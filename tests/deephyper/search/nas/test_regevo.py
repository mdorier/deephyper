import pytest
import numpy as np
from deephyper.benchmark.nas import linearReg
from deephyper.benchmark.nas import linearRegHybrid
from deephyper.evaluator import Evaluator
from deephyper.nas.run import run_debug_arch
from deephyper.search.nas import RegularizedEvolution


def test_regovo_with_hp():

    create_evaluator = lambda: Evaluator.create(
        run_debug_arch, method="process", method_kwargs={"num_workers": 1}
    )

    with pytest.raises(ValueError):  # timeout should be an int
        search = RegularizedEvolution(
            linearRegHybrid.Problem, create_evaluator(), random_state=42
        )


def test_regevo_without_hp():

    create_evaluator = lambda: Evaluator.create(
        run_debug_arch, method="process", method_kwargs={"num_workers": 1}
    )

    search = RegularizedEvolution(
        linearReg.Problem,
        create_evaluator(),
        random_state=42,
    )

    res1 = search.search(max_evals=4)
    res1_array = res1[["arch_seq"]].to_numpy()

    search.search(max_evals=100, timeout=1)

    search = RegularizedEvolution(
        linearReg.Problem,
        create_evaluator(),
        random_state=42,
    )
    res2 = search.search(max_evals=4)
    res2_array = res2[["arch_seq"]].to_numpy()

    assert np.array_equal(res1_array, res2_array)


if __name__ == "__main__":
    # test_regovo_with_hp()
    test_regevo_without_hp()
