```sh
cover-agent \
  --source-file-path "app.py" \
  --test-file-path "test_app.py" \
  --project-root "." \
  --code-coverage-report-path "coverage.xml" \
  --test-command "pytest --cov=. --cov-report=xml --cov-report=term" \
  --test-command-dir "." \
  --coverage-type "cobertura" \
  --desired-coverage 99 \
  --max-iterations 7 \
  --prompt-path "prompt.json" \
  --additional-instructions "However, do not assert exception messages or any string-based messages in assertions, as these may lead to test failures due to minor variations." \
  --model "gpt-4o-mini"
```