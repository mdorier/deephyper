import logging
import os
import pathlib
import signal
import time

import numpy as np
import pandas as pd
import ray
import skopt

from mpi4py import MPI
from deephyper.core.exceptions import SearchTerminationError


class History:
    """History"""

    def __init__(self) -> None:
        self._list_x = []  # vector of hyperparameters
        self._list_y = []  # objective values
        self._keys_infos = []  # keys
        self._list_infos = []  # values

    def append_keys_infos(self, k: list):
        self._keys_infos.extend(k)

    def get_keys_infos(self) -> list:
        return self._keys_infos

    def append(self, x, y, infos):
        self._list_x.append(x)
        self._list_y.append(y)
        self._list_infos.append(infos)

    def length(self):
        return len(self._list_x)

    def value(self):
        return self._list_x[:], self._list_y[:]

    def infos(self):
        list_infos = np.array(self._list_infos).T
        infos = {k: v for k, v in zip(self._keys_infos, list_infos)}
        return self._list_x, self._list_y, infos


class DMBSMPI:
    """Distributed Model-Based Search based on the `Scikit-Optimized Optimizer <https://scikit-optimize.github.io/stable/modules/generated/skopt.Optimizer.html#skopt.Optimizer>`_.

    Args:
        problem (HpProblem): Hyperparameter problem describing the search space to explore.
        evaluator (Evaluator): An ``Evaluator`` instance responsible of distributing the tasks.
        random_state (int, optional): Random seed. Defaults to ``None``.
        log_dir (str, optional): Log directory where search's results are saved. Defaults to ``"."``.
        verbose (int, optional): Indicate the verbosity level of the search. Defaults to ``0``.
    """

    def __init__(
        self,
        problem,
        run_function,
        random_state: int = None,
        log_dir: str = ".",
        verbose: int = 0,
        comm=None,
        run_function_kwargs: dict = None,
    ):

        self._problem = problem
        self._run_function = run_function
        self._run_function_kwargs = (
            {} if run_function_kwargs is None else run_function_kwargs
        )

        if type(random_state) is int:
            self._seed = random_state
            self._random_state = np.random.RandomState(random_state)
        elif isinstance(random_state, np.random.RandomState):
            self._random_state = random_state
        else:
            self._random_state = np.random.RandomState()

        # Create logging directory if does not exist
        self._log_dir = os.path.abspath(log_dir)
        pathlib.Path(log_dir).mkdir(parents=False, exist_ok=True)

        self._verbose = verbose

        # mpi
        self._comm = comm if comm else MPI.COMM_WORLD
        self._rank = self._comm.Get_rank()
        self._size = self._comm.Get_size()
        logging.info(f"DMBSMPI has {self._size} worker(s)")

        # set random state for given rank
        self._rank_seed = self._random_state.randint(
            self._random_state.randint(0, 2**32), size=self._size
        )[self._rank]

        self._timestamp = time.time()

        self._history = History()
        self._opt = None
        self._opt_space = self._problem.space
        self._opt_kwargs = dict(
            dimensions=self._opt_space,
            base_estimator="RF",
            acq_func="LCB",
            acq_optimizer="boltzmann_sampling",
            acq_optimizer_kwargs={"n_points": 10000, "boltzmann_gamma": 1},
            n_initial_points=1,
            random_state=self._rank_seed,
        )

    def send_all(self, x, y, infos):
        logging.info("Sending to all...")
        t1 = time.time()

        data = (x, y, infos)
        req_send = [
            self._comm.isend(data, dest=i) for i in range(self._size) if i != self._rank
        ]
        MPI.Request.waitall(req_send)

        logging.info(f"Sending to all done in {time.time() - t1:.4f} sec.")

    def recv_any(self) -> list:
        logging.info("Receiving from any...")
        t1 = time.time()

        n_received = 0
        received_any = self._size > 1

        while received_any:

            received_any = False
            req_recv = [
                self._comm.irecv(source=i) for i in range(self._size) if i != self._rank
            ]

            for req in req_recv:
                done, data = req.test()
                if done:
                    received_any = True
                    n_received += 1
                    x, y, infos = data
                    self._history.append(x, y, infos)
                else:
                    req.cancel()

        logging.info(
            f"Received {n_received} configurations in {time.time() - t1:.4f} sec."
        )

    def terminate(self):
        """Terminate the search.

        Raises:
            SearchTerminationError: raised when the search is terminated with SIGALARM
        """
        logging.info("Search is being stopped!")

        raise SearchTerminationError

    def _set_timeout(self, timeout=None):
        def handler(signum, frame):
            self.terminate()

        signal.signal(signal.SIGALRM, handler)

        if np.isscalar(timeout) and timeout > 0:
            signal.alarm(timeout)

    def search(self, max_evals: int = -1, timeout: int = None):
        """Execute the search algorithm.

        Args:
            max_evals (int, optional): The maximum number of evaluations of the run function to perform before stopping the search. Defaults to ``-1``, will run indefinitely.
            timeout (int, optional): The time budget (in seconds) of the search before stopping. Defaults to ``None``, will not impose a time budget.

        Returns:
            DataFrame: a pandas DataFrame containing the evaluations performed.
        """
        if timeout is not None:
            if type(timeout) is not int:
                raise ValueError(
                    f"'timeout' shoud be of type'int' but is of type '{type(timeout)}'!"
                )
            if timeout <= 0:
                raise ValueError(f"'timeout' should be > 0!")

        self._set_timeout(timeout)

        try:
            self._search(max_evals, timeout)
        except SearchTerminationError:
            pass

        # TODO
        path_results = os.path.join(self._log_dir, "results.csv")
        results = self.gather_results()
        results.to_csv(path_results)
        return results

    def _setup_optimizer(self):
        # if self._fitted:
        #     self._opt_kwargs["n_initial_points"] = 0
        self._opt = skopt.Optimizer(**self._opt_kwargs)

    def _search(self, max_evals, timeout):

        if self._opt is None:
            self._setup_optimizer()

        logging.info("Asking 1 configuration...")
        t1 = time.time()
        x = self._opt.ask()
        logging.info(f"Asking took {time.time() - t1:.4f} sec.")

        logging.info("Executing the run-function...")
        t1 = time.time()
        y = self._run_function(self.to_dict(x), **self._run_function_kwargs)
        logging.info(f"Execution took {time.time() - t1:.4f} sec.")

        infos = [self._rank]
        self._history.append_keys_infos(["worker_rank"])

        # code to manage the @profile decorator
        profile_keys = ["objective", "timestamp_start", "timestamp_end"]
        if isinstance(y, dict) and all(k in y for k in profile_keys):
            profile = y
            y = profile["objective"]
            timestamp_start = profile["timestamp_start"] - self._timestamp
            timestamp_end = profile["timestamp_end"] - self._timestamp
            infos.extend([timestamp_start, timestamp_end])

            self._history.append_keys_infos(profile_keys[1:])

        y = -y  #! we do maximization

        self._history.append(x, y, infos)
        self.send_all(x, y, infos)

        while max_evals < 0 or self._history.length() < max_evals:

            # collect x, y from other nodes (history)
            self.recv_any()
            hist_X, hist_y = self._history.value()
            n_new = len(hist_X) - len(self._opt.Xi)

            # fit optimizer
            # self._opt.Xi = []
            # self._opt.yi = []
            # self._opt.sampled = hist_X  # avoid duplicated samples

            logging.info("Fitting the optimizer...")
            t1 = time.time()
            self._opt.tell(hist_X[-n_new:], hist_y[-n_new])
            logging.info(f"Fitting took {time.time() - t1:.4f} sec.")

            # ask next configuration
            logging.info("Asking 1 configuration...")
            t1 = time.time()
            x = self._opt.ask()
            logging.info(f"Asking took {time.time() - t1:.4f} sec.")
            
            logging.info("Executing the run-function...")
            t1 = time.time()
            y = self._run_function(self.to_dict(x), **self._run_function_kwargs)
            logging.info(f"Execution took {time.time() - t1:.4f} sec.")
            infos = [self._rank]

            # code to manage the profile decorator
            profile_keys = ["objective", "timestamp_start", "timestamp_end"]
            if isinstance(y, dict) and all(k in y for k in profile_keys):
                profile = y
                y = profile["objective"]
                timestamp_start = profile["timestamp_start"] - self._timestamp
                timestamp_end = profile["timestamp_end"] - self._timestamp
                infos.extend([timestamp_start, timestamp_end])

            y = -y  #! we do maximization

            # update shared history
            self._history.append(x, y, infos)
            self.send_all(x, y, infos)

    def to_dict(self, x: list) -> dict:
        """Transform a list of hyperparameter values to a ``dict`` where keys are hyperparameters names and values are hyperparameters values.

        :meta private:

        Args:
            x (list): a list of hyperparameter values.

        Returns:
            dict: a dictionnary of hyperparameter names and values.
        """
        res = {}
        hps_names = self._problem.hyperparameter_names
        for i in range(len(x)):
            res[hps_names[i]] = x[i]
        return res

    def gather_results(self):
        x_list, y_list, infos_dict = self._history.infos()
        x_list = np.transpose(np.array(x_list))
        y_list = -np.array(y_list)

        results = {
            hp_name: x_list[i]
            for i, hp_name in enumerate(self._problem.hyperparameter_names)
        }
        results.update(dict(objective=y_list, **infos_dict))
        results = pd.DataFrame(results)
        return results