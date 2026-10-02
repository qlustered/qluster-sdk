__defaults__({python_tests: dict(batch_compatibility_tag="qluster-sdk")})

python_test_utils(
    name="test_utils",
)

python_tests(
    overrides={
        "test_readme.py": {"dependencies": ["qluster-sdk:readme"]},
    },
)
