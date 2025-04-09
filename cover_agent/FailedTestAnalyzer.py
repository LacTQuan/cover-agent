import os
import yaml
from typing import List, Dict, Any
from cover_agent.AICaller import AICaller
from cover_agent.CustomLogger import CustomLogger
from cover_agent.PromptBuilder import PromptBuilder


class FailedTestAnalyzer:
    def __init__(self, source_file_path: str, test_file_path: str, llm_model: str,
                 code_coverage_report_path: str = "", test_command: str = "",
                 test_command_dir: str = "", included_files: str = None,
                 coverage_type: str = "", additional_instructions: str = "",
                 api_base: str = ""):
        """
        Initialize the FailedTestAnalyzer.

        Args:
            source_file_path (str): Path to the source file being tested
            test_file_path (str): Path to the test file
            llm_model (str): The LLM model to use for analysis
            code_coverage_report_path (str, optional): Path to the code coverage report
            test_command (str, optional): Command to run tests
            test_command_dir (str, optional): Directory to run test command from
            included_files (str, optional): Additional files to include in analysis
            coverage_type (str, optional): Type of coverage to analyze
            additional_instructions (str, optional): Additional instructions for analysis
            api_base (str, optional): API base URL for the LLM. Defaults to "".
        """
        self.source_file_path = source_file_path
        self.test_file_path = test_file_path
        self.llm_model = llm_model
        self.api_base = api_base
        self.logger = CustomLogger.get_logger(__name__)

        # Initialize AI caller
        self.ai_caller = AICaller(
            model=llm_model, prompt_path='./prompt.txt', api_base=api_base)

        # Determine language based on file extension
        file_ext = os.path.splitext(source_file_path)[1].lower()
        language = ""
        if file_ext == ".py":
            language = "python"
        elif file_ext in [".js", ".ts"]:
            language = "javascript"
        elif file_ext in [".java"]:
            language = "java"
        # Add more language mappings as needed

        # Initialize prompt builder
        self.prompt_builder = PromptBuilder(
            source_file_path=source_file_path,
            test_file_path=test_file_path,
            code_coverage_report=code_coverage_report_path if code_coverage_report_path else "",
            included_files=included_files if included_files else "",
            additional_instructions=additional_instructions,
            failed_test_runs="",
            mutation_test_results="",
            language=language,
            testing_framework="",
            project_root=os.path.dirname(os.path.dirname(
                source_file_path)) if os.path.dirname(source_file_path) else "",
        )

    def analyze_failed_tests(self, failed_tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze failed tests to identify potential source code issues.

        Args:
            failed_tests (List[Dict[str, Any]]): List of failed test cases with their code and error messages

        Returns:
            List[Dict[str, Any]]: List of tests that reveal potential source code issues
        """
        if not failed_tests:
            return []

        # Read source file
        with open(self.source_file_path, 'r') as f:
            source_code = f.read()

        # Format the failed tests for the AI analysis
        formatted_tests = []
        for i, test in enumerate(failed_tests):
            formatted_test = {
                "index": i + 1,
                "test_name": test['code'].get('test_name', '').strip(),
                "test_code": test['code'].get('test_code', '').strip(),
                "error_message": test.get('error_message', '').strip(),
                "lines_to_cover": test['code'].get('lines_to_cover', '').strip()
            }
            formatted_tests.append(formatted_test)
        
        # Update the source code in the prompt builder
        self.prompt_builder.source_file = source_code

        # Build prompt for analysis, passing the formatted tests directly as a parameter
        prompt = self.prompt_builder.build_prompt_custom(
            file="analyze_failed_tests", 
            failed_tests=formatted_tests
        )
        
        # print(f"Prompt for LLM:\n{prompt}\n")

        # Call LLM for analysis
        response, _, _ = self.ai_caller.call_model(prompt=prompt)

        # remove the ```yaml and ``` from the response
        response = response.strip().split('```yaml')[1].strip()
        response = response.split('```')[0].strip()

        try:
            # Parse the YAML response
            analysis_result = yaml.safe_load(response)
            potential_issues = analysis_result.get('potential_issues', [])

            # Filter failed tests to only include those with potential issues
            relevant_tests = []
            for issue in potential_issues:
                test_index = issue['test_index'] - 1  # Convert to 0-based index
                if 0 <= test_index < len(failed_tests):
                    relevant_tests.append({
                        'test': failed_tests[test_index],
                        'issue_type': issue['issue_type'],
                        'description': issue['brief_description']
                    })

            return relevant_tests

        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing LLM response: {e}")
            return []

    def save_relevant_tests(self, relevant_tests: List[Dict[str, Any]], output_file: str):
        """
        Save tests that reveal potential source code issues to a separate file.

        Args:
            relevant_tests (List[Dict[str, Any]]): List of relevant tests with their issues
            output_file (str): Path to save the relevant tests
        """
        if not relevant_tests:
            return

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, 'w') as f:
            f.write("# Tests Revealing Potential Source Code Issues\n\n")
            for test_info in relevant_tests:
                test = test_info['test']
                f.write(f"## Issue Type: {test_info['issue_type']}\n")
                f.write(f"### Description: {test_info['description']}\n\n")
                
                # Extract test information from the code section
                test_name = test['code'].get('test_name', '').strip()
                test_code = test['code'].get('test_code', '').strip()
                lines_to_cover = test['code'].get('lines_to_cover', '').strip()
                
                f.write(f"**Test Name:** {test_name}\n\n")
                if lines_to_cover:
                    f.write(f"**Lines to Cover:** {lines_to_cover}\n\n")
                
                f.write("**Test Code:**\n```python\n")
                f.write(test_code)
                f.write("\n```\n\n")
                