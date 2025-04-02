import logging
import os

from jinja2 import Environment, StrictUndefined

from cover_agent.AICaller import AICaller
from cover_agent.settings.config_loader import get_settings
from cover_agent.utils import load_yaml

MAX_TESTS_PER_RUN = 4

# Markdown text used as conditional appends
ADDITIONAL_INCLUDES_TEXT = """
## Additional Includes
Here are the additional files needed to provide context for the source code:
======
{included_files}
======
"""

ADDITIONAL_INSTRUCTIONS_TEXT = """
## Additional Instructions
======
{additional_instructions}
======
"""

FAILED_TESTS_TEXT = """
## Previous Iterations Failed Tests
Below is a list of failed tests that were generated in previous iterations. Do not generate the same tests again, and take the failed tests into account when generating new tests.
======
{failed_test_runs}
======
"""

MUTATION_TESTS_TEXT = """
## Mutation Testing Results
The following are the results from mutation testing, which identifies weaknesses in our test suite. These results are critical for improving test quality.
======
{mutation_test_results}
======
"""


class PromptBuilder:
    def __init__(
        self,
        source_file_path: str,
        test_file_path: str,
        code_coverage_report: str,
        included_files: str = "",
        additional_instructions: str = "",
        failed_test_runs: str = "",
        mutation_test_results: str = "",
        language: str = "python",
        testing_framework: str = "NOT KNOWN",
        project_root: str = "",
        validator = None,
    ):
        """
        The `PromptBuilder` class is responsible for building a formatted prompt string by replacing placeholders with the actual content of files read during initialization. It takes in various paths and settings as parameters and provides a method to generate the prompt.

        Attributes:
            prompt_template (str): The content of the prompt template file.
            source_file (str): The content of the source file.
            test_file (str): The content of the test file.
            code_coverage_report (str): The code coverage report.
            included_files (str): The formatted additional includes section.
            additional_instructions (str): The formatted additional instructions section.
            failed_test_runs (str): The formatted failed test runs section.
            language (str): The programming language of the source and test files.
            validator (UnitTestValidator): The validator instance to get coverage and mutation score information.

        Methods:
            __init__(self, prompt_template_path: str, source_file_path: str, test_file_path: str, code_coverage_report: str, included_files: str = "", additional_instructions: str = "", failed_test_runs: str = "")
                Initializes the `PromptBuilder` object with the provided paths and settings.

            _read_file(self, file_path)
                Helper method to read the content of a file.

            build_prompt(self)
                Replaces placeholders with the actual content of files read during initialization and returns the formatted prompt string.
        """
        self.project_root = project_root
        self.source_file_path = source_file_path
        self.test_file_path = test_file_path
        self.source_file_name_rel = os.path.relpath(source_file_path, project_root)
        self.test_file_name_rel = os.path.relpath(test_file_path, project_root)
        self.source_file = self._read_file(source_file_path)
        self.test_file = self._read_file(test_file_path)
        self.code_coverage_report = code_coverage_report
        self.language = language
        self.testing_framework = testing_framework
        self.validator = validator

        # add line numbers to each line in 'source_file'. start from 1
        self.source_file_numbered = "\n".join(
            [f"{i + 1} {line}" for i, line in enumerate(self.source_file.split("\n"))]
        )
        self.test_file_numbered = "\n".join(
            [f"{i + 1} {line}" for i, line in enumerate(self.test_file.split("\n"))]
        )

        # Conditionally fill in optional sections
        self.included_files = (
            ADDITIONAL_INCLUDES_TEXT.format(included_files=included_files)
            if included_files
            else ""
        )
        self.additional_instructions = (
            ADDITIONAL_INSTRUCTIONS_TEXT.format(
                additional_instructions=additional_instructions
            )
            if additional_instructions
            else ""
        )
        self.failed_test_runs = (
            FAILED_TESTS_TEXT.format(failed_test_runs=failed_test_runs)
            if failed_test_runs
            else ""
        )
        
        self.mutation_test_results = (
            MUTATION_TESTS_TEXT.format(mutation_test_results=mutation_test_results)
            if mutation_test_results
            else ""
        )

        self.stdout_from_run = ""
        self.stderr_from_run = ""
        self.processed_test_file = ""

    def _read_file(self, file_path):
        """
        Helper method to read file contents.

        Parameters:
            file_path (str): Path to the file to be read.

        Returns:
            str: The content of the file.
        """
        try:
            with open(file_path, "r") as f:
                return f.read()
        except Exception as e:
            return f"Error reading {file_path}: {e}"

    def build_prompt(self) -> dict:
        variables = {
            "source_file_name": self.source_file_name_rel,
            "test_file_name": self.test_file_name_rel,
            "source_file_numbered": self.source_file_numbered,
            "test_file_numbered": self.test_file_numbered,
            "source_file": self.source_file,
            "test_file": self.test_file,
            "code_coverage_report": self.code_coverage_report,
            "additional_includes_section": self.included_files,
            "failed_tests_section": self.failed_test_runs,
            "mutation_test_results": self.mutation_test_results,
            "additional_instructions_text": self.additional_instructions,
            "language": self.language,
            "max_tests": MAX_TESTS_PER_RUN,
            "testing_framework": self.testing_framework,
            "stdout": self.stdout_from_run,
            "stderr": self.stderr_from_run,
            "current_coverage": round(self.validator.current_coverage * 100, 2) if self.validator else 0,
            "current_mutation_score": round(self.validator.current_mutation_score, 2) if self.validator else 0,
            "desired_coverage": self.validator.desired_coverage if self.validator else 70,
            "desired_mutation_score": self.validator.desired_mutation_score if self.validator else 70,
        }
        logging.info(f'MUTATION_TEST_RESULTS: {self.mutation_test_results}')
        environment = Environment(undefined=StrictUndefined)
        try:
            system_prompt = environment.from_string(
                get_settings().test_generation_prompt.system
            ).render(variables)
            user_prompt = environment.from_string(
                get_settings().test_generation_prompt.user
            ).render(variables)
        except Exception as e:
            logging.error(f"Error rendering prompt: {e}")
            return {"system": "", "user": ""}

        # print(f"#### user_prompt:\n\n{user_prompt}")
        return {"system": system_prompt, "user": user_prompt}

    def build_prompt_custom(self, file) -> dict:
        """
        Builds a custom prompt by replacing placeholders with actual content from files and settings.

        Parameters:
            file (str): The file to retrieve settings for building the prompt.

        Returns:
            dict: A dictionary containing the system and user prompts.
        """
        variables = {
            "source_file_name": self.source_file_name_rel,
            "test_file_name": self.test_file_name_rel,
            "source_file_numbered": self.source_file_numbered,
            "test_file_numbered": self.test_file_numbered,
            "source_file": self.source_file,
            "test_file": self.test_file,
            "code_coverage_report": self.code_coverage_report,
            "additional_includes_section": self.included_files,
            "failed_tests_section": self.failed_test_runs,
            "mutation_test_results": self.mutation_test_results,
            "additional_instructions_text": self.additional_instructions,
            "language": self.language,
            "max_tests": MAX_TESTS_PER_RUN,
            "testing_framework": self.testing_framework,
            "stdout": self.stdout_from_run,
            "stderr": self.stderr_from_run,
            "processed_test_file": self.processed_test_file,
        }
        environment = Environment(undefined=StrictUndefined)
        try:
            settings = get_settings().get(file)
            if settings is None or not hasattr(settings, "system") or not hasattr(
                settings, "user"
            ):
                logging.error(f"Could not find settings for prompt file: {file}")
                return {"system": "", "user": ""}
            system_prompt = environment.from_string(settings.system).render(variables)
            user_prompt = environment.from_string(settings.user).render(variables)
        except Exception as e:
            logging.error(f"Error rendering prompt: {e}")
            return {"system": "", "user": ""}

        return {"system": system_prompt, "user": user_prompt}


def adapt_test_command_for_a_single_test_via_ai(args, test_file_relative_path, test_command):
    try:
        variables = {"project_root_dir": args.test_command_dir,
                     "test_file_relative_path": test_file_relative_path,
                     "test_command": test_command,
                     }
        ai_caller = AICaller(model=args.model, prompt_path=args.prompt_path)
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().adapt_test_command_for_a_single_test_via_ai.system).render(
            variables)
        user_prompt = environment.from_string(get_settings().adapt_test_command_for_a_single_test_via_ai.user).render(
            variables)
        response, prompt_token_count, response_token_count = (
            ai_caller.call_model(prompt={"system": system_prompt, "user": user_prompt}, stream=False)
        )
        response_yaml = load_yaml(response)
        new_command_line = response_yaml["new_command_line"].strip()
        return new_command_line
    except Exception as e:
        logging.error(f"Error adapting test command: {e}")
        return None