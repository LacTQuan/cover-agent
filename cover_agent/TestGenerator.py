def generate_tests(self, max_iterations=10):
    """
    Generate tests using the LLM.

    Args:
        max_iterations (int): The maximum number of iterations to run.

    Returns:
        bool: True if the test generation was successful, False otherwise.
    """
    for iteration in range(max_iterations):
        self.logger.info(f"Starting iteration {iteration + 1}/{max_iterations}")

        # Generate test code
        test_code = self._generate_test_code()
        if not test_code:
            self.logger.error("Failed to generate test code")
            continue

        # Validate the test
        success, reason = self.validator.validate_test(test_code)
        if success:
            self.logger.info("Test validation successful")
            self.logger.info(f"Current coverage: {self.validator.current_coverage:.2f}%")
            self.logger.info(f"Current mutation score: {self.validator.current_mutation_score:.2f}%")

            # Check if we've reached desired coverage
            coverage_goal_met = self.validator.current_coverage >= self.validator.desired_coverage

            # Check if we've reached desired mutation score
            mutation_goal_met = self.validator.current_mutation_score >= self.validator.desired_mutation_score
            
            # Determine if we've met our goals based on strict_mutation_score setting
            if self.validator.strict_mutation_score:
                # If strict, both goals must be met
                if coverage_goal_met and mutation_goal_met:
                    self.logger.info("Desired coverage and mutation score achieved")
                    return True
            else:
                # If not strict, only coverage goal needs to be met
                if coverage_goal_met:
                    self.logger.info("Desired coverage achieved")
                    if mutation_goal_met:
                        self.logger.info("Desired mutation score also achieved")
                    return True
        else:
            self.logger.error(f"Test validation failed: {reason}")

    return False

def _generate_test_code(self):
    """
    Generate test code using the LLM.

    Returns:
        str: The generated test code.
    """
    # Build the prompt
    prompt = self.prompt_builder.build_prompt()

    # Generate test code using the LLM
    response = self.llm_model.generate(prompt)
    if not response:
        return None

    # Extract test code from the response
    test_code = self._extract_test_code(response)
    if not test_code:
        return None

    return test_code 