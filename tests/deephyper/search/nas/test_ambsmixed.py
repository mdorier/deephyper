import numpy as np
from deephyper.benchmark.nas import linearReg
from deephyper.benchmark.nas import linearRegHybrid
from deephyper.evaluator import Evaluator
from deephyper.nas.run import run_debug_arch
from deephyper.search.nas import AMBSMixed


def test_ambsmixed_without_hp():

    create_evaluator = lambda: Evaluator.create(
        run_debug_arch, method="process", method_kwargs={"num_workers": 1}
    )

    search = AMBSMixed(
        linearReg.Problem, create_evaluator(), random_state=42
    )

    res1 = search.search(max_evals=4)
    res1_array = res1[["arch_seq"]].to_numpy()

    search.search(max_evals=100, timeout=1)

    search = AMBSMixed(
        linearReg.Problem,
        create_evaluator(),
        random_state=42,
    )
    res2 = search.search(max_evals=4)
    res2_array = res2[["arch_seq"]].to_numpy()

    assert np.array_equal(res1_array, res2_array)


def test_ambsmixed_with_hp():

    create_evaluator = lambda: Evaluator.create(
        run_debug_arch, method="process", method_kwargs={"num_workers": 1}
    )

    search = AMBSMixed(
        linearRegHybrid.Problem,
        create_evaluator(),
        random_state=42,
    )

    res1 = search.search(max_evals=4)
    res1_array = res1[["arch_seq"]].to_numpy()

    search.search(max_evals=100, timeout=1)

    search = AMBSMixed(
        linearRegHybrid.Problem,
        create_evaluator(),
        random_state=42,
    )
    res2 = search.search(max_evals=4)
    res2_array = res2[["arch_seq"]].to_numpy()

    assert np.array_equal(res1_array, res2_array)


if __name__ == "__main__":
    # test_ambsmixed_without_hp()
    test_ambsmixed_with_hp()
