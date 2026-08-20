from evals.evaluator import load_cases


def test_eval_cases_are_valid_and_unique():
    cases = load_cases()
    ids = [case["id"] for case in cases]
    assert len(cases) >= 10
    assert len(ids) == len(set(ids))
