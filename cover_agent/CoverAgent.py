import datetime
import os
import shutil
import sys
import wandb

from typing import List

from cover_agent.CustomLogger import CustomLogger
from cover_agent.PromptBuilder import adapt_test_command_for_a_single_test_via_ai
from cover_agent.ReportGenerator import ReportGenerator
from cover_agent.UnitTestGenerator import UnitTestGenerator
from cover_agent.UnitTestValidator import UnitTestValidator
from cover_agent.UnitTestDB import UnitTestDB
from cover_agent.FailedTestAnalyzer import FailedTestAnalyzer

class CoverAgent:
    def __init__(self, args):
        """
        Initialize the CoverAgent class with the provided arguments and run the test generation process.

        Parameters:
            args (Namespace): The parsed command-line arguments containing necessary information for test generation.

        Returns:
            None
        """
        self.args = args
        self.logger = CustomLogger.get_logger(__name__)

        self._validate_paths()
        self._duplicate_test_file()

        # To run only a single test file, we need to modify the test command
        self.parse_command_to_run_only_a_single_test(args)

        self.test_gen = UnitTestGenerator(
            source_file_path=args.source_file_path,
            test_file_path=args.test_file_output_path,
            project_root=args.project_root,
            code_coverage_report_path=args.code_coverage_report_path,
            test_command=args.test_command,
            test_command_dir=args.test_command_dir,
            included_files=args.included_files,
            coverage_type=args.coverage_type,
            additional_instructions=args.additional_instructions,
            llm_model=args.model,
            api_base=args.api_base,
            use_report_coverage_feature_flag=args.use_report_coverage_feature_flag,
        )

        self.test_validator = UnitTestValidator(
            source_file_path=args.source_file_path,
            test_file_path=args.test_file_output_path,
            project_root=args.project_root,
            code_coverage_report_path=args.code_coverage_report_path,
            test_command=args.test_command,
            test_command_dir=args.test_command_dir,
            included_files=args.included_files,
            coverage_type=args.coverage_type,
            desired_coverage=args.desired_coverage,
            additional_instructions=args.additional_instructions,
            llm_model=args.model,
            api_base=args.api_base,
            use_report_coverage_feature_flag=args.use_report_coverage_feature_flag,
            diff_coverage=args.diff_coverage,
            comparison_branch=args.branch,
            num_attempts=args.run_tests_multiple_times,
            desired_mutation_score=args.desired_mutation_score,
            strict_mutation_score=args.strict_mutation_score,
        )
        
        self.failed_test_analyzer = FailedTestAnalyzer(
            source_file_path=args.source_file_path,
            test_file_path=args.test_file_output_path,
            llm_model=args.model,
            code_coverage_report_path=args.code_coverage_report_path,
            test_command=args.test_command,
            test_command_dir=args.test_command_dir,
            included_files=args.included_files,
            coverage_type=args.coverage_type,
            additional_instructions=args.additional_instructions,
            api_base=args.api_base,
        )

    def parse_command_to_run_only_a_single_test(self, args):
        test_command = args.test_command
        new_command_line = None
        if hasattr(args, 'run_each_test_separately') and args.run_each_test_separately:
            test_file_relative_path = os.path.relpath(args.test_file_output_path, args.project_root)
            if 'pytest' in test_command:  # coverage run -m pytest tests  --cov=/Users/talrid/Git/cover-agent --cov-report=xml --cov-report=term --log-cli-level=INFO --timeout=30
                try:
                    ind1 = test_command.index('pytest')
                    ind2 = test_command[ind1:].index('--')
                    new_command_line = f"{test_command[:ind1]}pytest {test_file_relative_path} {test_command[ind1 + ind2:]}"
                except ValueError:
                    print(f"Failed to adapt test command for running a single test: {test_command}")
            else:
                new_command_line = adapt_test_command_for_a_single_test_via_ai(args, test_file_relative_path, test_command)
        if new_command_line:
            args.test_command_original = test_command
            args.test_command = new_command_line
            print(f"Converting test command: `{test_command}`\n to run only a single test: `{new_command_line}`")

    def _validate_paths(self):
        """
        Validate the paths provided in the arguments.

        Raises:
            FileNotFoundError: If the source file or test file is not found at the specified paths.
        """
        # Ensure the source file exists
        if not os.path.isfile(self.args.source_file_path):
            raise FileNotFoundError(
                f"Source file not found at {self.args.source_file_path}"
            )
        # Ensure the test file exists
        if not os.path.isfile(self.args.test_file_path):
            raise FileNotFoundError(
                f"Test file not found at {self.args.test_file_path}"
            )

        # Ensure the project root exists
        if self.args.project_root and not os.path.isdir(self.args.project_root):
            raise FileNotFoundError(
                f"Project root not found at {self.args.project_root}"
            )

        # Create default DB file if not provided
        if not self.args.log_db_path:
            self.args.log_db_path = "cover_agent_unit_test_runs.db"
        # Connect to the test DB
        self.test_db = UnitTestDB(db_connection_string=f"sqlite:///{self.args.log_db_path}")

    def _duplicate_test_file(self):
        """
        Initialize the CoverAgent class with the provided arguments and run the test generation process.

        Parameters:
            args (Namespace): The parsed command-line arguments containing necessary information for test generation.

        Returns:
            None
        """
        # If the test file output path is set, copy the test file there
        if self.args.test_file_output_path != "":
            shutil.copy(self.args.test_file_path, self.args.test_file_output_path)
        else:
            # Otherwise, set the test file output path to the current test file
            self.args.test_file_output_path = self.args.test_file_path

    def init(self):
        """
        Prepare for test generation process

        1. Initialize the Weights & Biases run if the WANDS_API_KEY environment variable is set.
        2. Initialize variables to track progress.
        3. Run the initial test suite analysis.
        
        """
        # Check if user has exported the WANDS_API_KEY environment variable
        if "WANDB_API_KEY" in os.environ:
            # Initialize the Weights & Biases run
            wandb.login(key=os.environ["WANDB_API_KEY"])
            time_and_date = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            run_name = f"{self.args.model}_" + time_and_date
            wandb.init(project="cover-agent", name=run_name)

        # Run initial test suite analysis
        self.test_validator.initial_test_suite_analysis()
        failed_test_runs, mutation_test_results, language, test_framework, coverage_report = self.test_validator.get_coverage()
        self.test_gen.build_prompt(failed_test_runs, mutation_test_results, language, test_framework, coverage_report)

        return failed_test_runs, mutation_test_results, language, test_framework, coverage_report

    def run_test_gen(self, failed_test_runs: List, mutation_test_results: str, language: str, test_framework: str, coverage_report: str):
        """
        Run the test generation process.

        This method performs the following steps:

        1. Loop until desired coverage is reached or maximum iterations are met.
        2. Generate new tests.
        3. Loop through each new test and validate it.
        4. Insert the test result into the database.
        5. Increment the iteration count.
        6. Check if the desired coverage has been reached.
        7. If the desired coverage has been reached, log the final coverage.
        8. If the maximum iteration limit is reached, log a failure message if strict coverage is specified.
        9. Provide metrics on total token usage.
        10. Generate a report.
        11. Finish the Weights & Biases run if it was initialized.
        """
        # Initialize variables to track progress
        iteration_count = 0

        # Loop until desired coverage is reached or maximum iterations are met
        while iteration_count < self.args.max_iterations:
            # Log the current coverage
            self.log_coverage()

            # Generate new tests
            generated_tests_dict = self.test_gen.generate_tests(failed_test_runs, mutation_test_results, language, test_framework, coverage_report)

            # Loop through each new test and validate it
            for generated_test in generated_tests_dict.get("new_tests", []):
                # Validate the test and record the result
                test_result = self.test_validator.validate_test(generated_test)

                # Insert the test result into the database
                test_result["prompt"] = self.test_gen.prompt["user"]
                self.test_db.insert_attempt(test_result)

            # Increment the iteration count
            iteration_count += 1

            # Check if the desired coverage has been reached
            failed_test_runs, mutation_test_results, language, test_framework, coverage_report = self.test_validator.get_coverage()

            # print(f"Iteration {iteration_count}: Failed test runs: {failed_test_runs}")

            # If failed tests are found, analyze them
            if failed_test_runs:
                # failed_test_runs is already in the format needed by the analyzer
                self.logger.info(f"Analyzing {len(failed_test_runs)} failed tests for potential source code issues")
                relevant_tests = self.failed_test_analyzer.analyze_failed_tests(failed_test_runs)
                
                if relevant_tests:
                    # Save the analysis results
                    output_dir = os.path.join(self.args.project_root, "potential_source_code_issues")
                    os.makedirs(output_dir, exist_ok=True)

                    output_file = os.path.join(
                        output_dir,
                        f"failed_test_analysis_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                    )
                    self.failed_test_analyzer.save_relevant_tests(relevant_tests, output_file)
                    self.logger.info(f"Found {len(relevant_tests)} tests that reveal potential source code issues")
                    self.logger.info(f"Analysis results saved to {output_file}")
            
            # Determine if we've met our goals based on strict_mutation_score setting
            coverage_goal_met = self.test_validator.current_coverage >= (self.test_validator.desired_coverage / 100)
            mutation_goal_met = self.test_validator.current_mutation_score >= self.test_validator.desired_mutation_score
            
            if self.test_validator.strict_mutation_score:
                # If strict, both goals must be met
                if coverage_goal_met and mutation_goal_met:
                    break
            else:
                # If not strict, only coverage goal needs to be met
                if coverage_goal_met:
                    break

        # Log the final coverage and mutation score
        if self.test_validator.current_coverage >= (self.test_validator.desired_coverage / 100):
            coverage_message = f"Reached above target coverage of {self.test_validator.desired_coverage}% (Current Coverage: {round(self.test_validator.current_coverage * 100, 2)}%)"
            
            if self.test_validator.strict_mutation_score:
                if self.test_validator.current_mutation_score >= self.test_validator.desired_mutation_score:
                    self.logger.info(f"{coverage_message} and mutation score of {self.test_validator.current_mutation_score:.2f}% in {iteration_count} iterations.")
                else:
                    self.logger.info(f"{coverage_message} but did not reach target mutation score of {self.test_validator.desired_mutation_score}% (Current: {self.test_validator.current_mutation_score:.2f}%) in {iteration_count} iterations.")
            else:
                self.logger.info(f"{coverage_message} in {iteration_count} iterations. Current mutation score: {self.test_validator.current_mutation_score:.2f}%")
                
        elif iteration_count == self.args.max_iterations:
            if self.args.diff_coverage:
                failure_message = f"Reached maximum iteration limit without achieving desired diff coverage. Current Coverage: {round(self.test_validator.current_coverage * 100, 2)}%"
            else:
                failure_message = f"Reached maximum iteration limit without achieving desired coverage. Current Coverage: {round(self.test_validator.current_coverage * 100, 2)}%, Current Mutation Score: {self.test_validator.current_mutation_score:.2f}%"
            if self.args.strict_coverage:
                # User requested strict coverage (similar to "--cov-fail-under in pytest-cov"). Fail with exist code 2.
                self.logger.error(failure_message)
                sys.exit(2)
            elif self.test_validator.strict_mutation_score and self.test_validator.current_mutation_score < self.test_validator.desired_mutation_score:
                # User requested strict mutation score and we haven't met the goal. Fail with exit code 3.
                self.logger.error(f"Failed to achieve desired mutation score of {self.test_validator.desired_mutation_score}%. Current mutation score: {self.test_validator.current_mutation_score:.2f}%")
                sys.exit(3)
            else:
                self.logger.info(failure_message)

        # Provide metrics on total token usage
        self.logger.info(
            f"Total number of input tokens used for LLM model {self.test_gen.ai_caller.model}: {self.test_gen.total_input_token_count + self.test_validator.total_input_token_count}"
        )
        self.logger.info(
            f"Total number of output tokens used for LLM model {self.test_gen.ai_caller.model}: {self.test_gen.total_output_token_count + self.test_validator.total_output_token_count}"
        )

        # Generate a report
        self.test_db.dump_to_report(self.args.report_filepath)

        # Finish the Weights & Biases run if it was initialized
        if "WANDB_API_KEY" in os.environ:
            wandb.finish()

    def log_coverage(self):
        if self.args.diff_coverage:
            self.logger.info(
                f"Current Diff Coverage: {round(self.test_validator.current_coverage * 100, 2)}%"
            )
        else:
            self.logger.info(
                f"Current Coverage: {round(self.test_validator.current_coverage * 100, 2)}%"
            )
        self.logger.info(f"Desired Coverage: {self.test_validator.desired_coverage}%")

    def run(self):
        failed_test_runs, mutation_test_results, language, test_framework, coverage_report = self.init()
        self.run_test_gen(failed_test_runs, mutation_test_results, language, test_framework, coverage_report)