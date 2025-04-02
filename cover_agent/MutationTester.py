from cover_agent.Runner import Runner
from cover_agent.utils import load_yaml
import yaml


class MutationTester:
  count = 0

  @staticmethod
  def increment_count():
    MutationTester.count += 1
    
  @staticmethod
  def get_count():
    return MutationTester.count
  
  def __init__(
      self,
      test_command: str = "mut.py",
      report_html_file: str = "./",
      report_yaml_file: str = "mut_report.yaml",
      src_dir: str = "src",
      test_dir: str = "test",
      project_root: str = ".",
  ):
    MutationTester.increment_count()
    
    self.test_command = test_command
    self.report_html_file = f'{MutationTester.get_count()}_mut'
    self.report_yaml_file = f'{MutationTester.get_count()}_{report_yaml_file}'
    self.src_dir = src_dir
    self.test_dir = test_dir
    self.project_root = project_root
    self.run_command = f"{self.test_command} --target {self.src_dir} --unit-test {self.test_dir} -m --runner pytest --report {self.report_yaml_file}"
    
    
  MUTATION_OPERATOR_MAP = {
    "AOD": "Arithmetic Operator Deletion",
    "AOR": "Arithmetic Operator Replacement",
    "ASR": "Assignment Operator Replacement",
    "BCR": "Break Continue Replacement",
    "COD": "Conditional Operator Deletion",
    "CRP": "Comparison Replacement",
    "DDL": "Decorator Deletion",
    "EHD": "Exception Handler Deletion",
    "EXS": "Exception Swallowing",
    "IHD": "Hiding Variable Deletion",
    "IOD": "Overriding Method Deletion",
    "IOP": "Overridden Method Calling Position Change",
    "LCR": "Logical Connector Replacement",
    "LOD": "Logical Operator Deletion",
    "ROR": "Relational Operator Replacement",
    "RSI": "Raise Statement Insertion",
    "SCR": "Slice Range Creation",
    "SIR": "Slice Index Remove",
    "SVD": "Self Variable Deletion",
    "ZIL": "Zero Iteration Loop",
  }
  
  def get_report_files(self):
    return self.report_html_file, self.report_yaml_file
    
  def get_operator_full_name(self, abbreviation: str) -> str:
    return self.MUTATION_OPERATOR_MAP.get(abbreviation.upper(), "Unknown operator")
  

  def get_run_command(self):
    return self.run_command

  def run(self):
    stdout, stderr, exit_code, time_of_test_command = Runner.run_command(
        self.run_command, self.project_root
    )

    return stdout, stderr, exit_code, time_of_test_command

  def python_module_constructor(loader, node):
    # Define how you want to handle the tag here
    value = loader.construct_scalar(node)
    # You could, for example, return a string or some object
    return f"Loaded Python module: {value}"

  yaml.add_constructor(
      u'tag:yaml.org,2002:python/module:app',
      python_module_constructor,
      Loader=yaml.SafeLoader
  )
  
  def load_report(self):
    retries = 2
    print(f"Reading {self.report_yaml_file}...")
    for attempt in range(retries + 1):
      try:
        with open(self.report_yaml_file, "r") as f:
          data = yaml.safe_load(f)
          print(f"Data loaded from {self.report_yaml_file}, length: {len(data)}")
          return data
      except Exception as e:
        if attempt < retries:
          print(f"Attempt to read {self.report_yaml_file} the {attempt + 1} times failed: {e}. Retrying...")
        else:
          print(f"Attempt to read {self.report_yaml_file} the {attempt + 1} times failed: {e}. No more retries.")
          return None
  
  def generate_prompt(self) -> str:
    yaml_data = self.load_report()
    if yaml_data is None:
      return ""
    
    # add a delay to allow the file to be read
    print(f"Data loaded, size: {len(yaml_data)}")
    
    if not yaml_data:
        raise ValueError("No data loaded. Call load_report() first.")

    # 1. Mutation Score
    coverage_data = yaml_data.get("coverage", {})
    all_nodes = coverage_data.get("all_nodes", 0)
    covered_nodes = coverage_data.get("covered_nodes", 0)
    # This 'mutation_score' is the % from the top-level
    mutation_score = yaml_data.get("mutation_score", 0)

    # 2. Mutations
    mutation_list = yaml_data.get("mutations", [])
    survived_mutants = []
    
    # Enhanced structure to store more details about each mutant
    mutant_details = []

    for mutation_item in mutation_list:
        status = mutation_item.get("status")
        # Each mutation_item can have multiple "mutations" sub-items
        sub_mutations = mutation_item.get("mutations", [])
        
        if status == "survived":
            # We'll gather line/operator from each sub-mutation
            for sub in sub_mutations:
                lineno = sub.get("lineno")
                operator = sub.get("operator")
                survived_mutants.append((lineno, operator))
                
                # Store detailed information about the mutant
                mutant_details.append({
                    "line": lineno,
                    "operator": operator,
                    "operator_description": self.get_operator_full_name(operator),
                })

    # 3. Build the prompt text
    prompt_lines = []
    prompt_lines.append("## Results of Mutation Testing")
    prompt_lines.append(f"**Mutation Score**: {mutation_score:.2f}%")
    prompt_lines.append(f"**Nodes Covered**: {covered_nodes}/{all_nodes}")
    
    if survived_mutants:
        prompt_lines.append("\n### Understanding Mutation Testing")
        prompt_lines.append("Mutation testing creates small changes (mutants) in the code to verify if tests can detect these changes.")
        prompt_lines.append("When a mutant 'survives', it means our tests couldn't detect that the code was modified, indicating a weakness in our test suite.")
        
        prompt_lines.append("\n### Surviving Mutants")
        for i, mutant in enumerate(mutant_details, start=1):
            prompt_lines.append(f"\n**{i}. Line {mutant['line']}: {mutant['operator_description']}**")
            
            # Add specific recommendations based on mutation operator type
            if mutant['operator'] == "ROR":
                prompt_lines.append("This mutant changed a relational operator (e.g., > to >=, == to !=). Your test should specifically verify boundary conditions.")
            elif mutant['operator'] in ["AOR", "AOD"]:
                prompt_lines.append("This mutant modified arithmetic operations. Your test should verify calculations with specific values that would fail if the operation is changed.")
            elif mutant['operator'] == "LCR":
                prompt_lines.append("This mutant changed logical connectors (e.g., && to ||). Your test should check conditions where both original and mutated connectors would behave differently.")
    else:
        prompt_lines.append("No surviving mutants! Great job.")


    prompt_lines.append("\n### Testing Goal")
    prompt_lines.append("Please generate or refine tests that will detect these surviving mutants. For each mutant:")
    prompt_lines.append("1. Create a test that will pass with the original code but fail with the mutated code")
    prompt_lines.append("2. Ensure each test checks the specific behavior that would be altered by the mutation")
    prompt_lines.append("3. Use descriptive test names that indicate what mutation they are targeting")
    prompt_lines.append("4. Include assertions that directly validate the behavior affected by the mutation")

    return "\n".join(prompt_lines)

