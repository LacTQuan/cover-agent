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
    self.run_command = f"{self.test_command} --target {self.src_dir} --unit-test {self.test_dir} -m --runner pytest --report {self.report_yaml_file} --report-html {self.report_html_file} --percentage 10"
    
    
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
          raise
  
  def generate_prompt(self) -> str:
    yaml_data = self.load_report()
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

    for mutation_item in mutation_list:
        status = mutation_item.get("status")
        # Each mutation_item can have multiple "mutations" sub-items
        sub_mutations = mutation_item.get("mutations", [])
        # We'll gather line/operator from each sub-mutation
        for sub in sub_mutations:
            lineno = sub.get("lineno")
            operator = sub.get("operator")
            if status == "survived":
                survived_mutants.append((lineno, operator))

    # 3. Build the prompt text
    prompt_lines = []
    prompt_lines.append("## Results of Mutation Testing")
    prompt_lines.append(f"**Mutation Score**: {mutation_score:.2f}%")
    prompt_lines.append(f"**Nodes Covered**: {covered_nodes}/{all_nodes}")

    if survived_mutants:
        prompt_lines.append("The following mutants **survived**:")
        for i, (line_no, op) in enumerate(survived_mutants, start=1):
            prompt_lines.append(f"{i}) line {line_no}, operator: {self.get_operator_full_name(op)}")
    else:
        prompt_lines.append("No surviving mutants! Great job.")


    prompt_lines.append("")
    prompt_lines.append("**Goal**: Please generate or refine tests so that these surviving mutants are killed.")
    prompt_lines.append("Focus on the lines and operators that survived. For each, we need a test scenario that fails if that mutation occurs.")

    return "\n".join(prompt_lines)

