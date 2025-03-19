import argparse
import logging
import os
import subprocess
from secure_code_agent.security_check import SecurityChecker
from secure_code_agent.refactor import CodeRefactor
from secure_code_agent.github_manager import GitHubManager
from secure_code_agent.email_report import EmailReporter
from secure_code_agent.utils import load_repo_files
from langchain_ollama import OllamaLLM
from langchain.tools import Tool
from langchain.agents import initialize_agent
from langchain.agents import AgentType

# Initialize LLM
llm = OllamaLLM(model="gemma3:1b", base_url="http://localhost:11434")

def clone_repo(repo_url, repo_path):
    if os.path.exists(repo_path):
        logging.info(f"Repository already exists at {repo_path}. Skipping clone.")
    else:
        logging.info(f"Cloning repository from {repo_url} to {repo_path}...")
        subprocess.run(["git", "clone", repo_url, repo_path], check=True)

def security_scan_tool(code: str):
    security_checker = SecurityChecker()
    return security_checker.analyze(code)

def refactor_code_tool(code: str, issues: str):
    refactorer = CodeRefactor()
    return refactorer.refactor(code, issues)

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')    
    parser = argparse.ArgumentParser(description="Secure Code Agent")
    parser.add_argument("--repo_url", help="GitHub repository URL (optional)")
    parser.add_argument("--path", required=True, help="Path to the repository")
    parser.add_argument("--branch_name", default="securedev_agent_fixes", help="Branch where AI agent will push the code")
    parser.add_argument("--do_send_email", default="true", help="Send email report if set")
    parser.add_argument("--receiver_email", default="", help="Recipient email (required if --do_send_email is set)")
    args = parser.parse_args()

    if args.do_send_email.lower() == "true" and len(args.receiver_email) == 0:
        logging.error("Error: --receiver_email argument is required when --do_send_email is set true")
        return

    if args.repo_url:
        clone_repo(args.repo_url, args.path)
    
    repo_path = args.path
    branch_name = args.branch_name
    files = load_repo_files(repo_path)

    security_tool = Tool(
        name="Security Scan",
        func=security_scan_tool,
        description="Scans code for security vulnerabilities"
    )
    
    refactor_tool = Tool(
        name="Code Refactor",
        func=refactor_code_tool,
        description="Refactors insecure code based on detected issues"
    )
    
    agent = initialize_agent(
        tools=[security_tool, refactor_tool],
        llm=llm,
        agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        verbose=True
    )

    findings = {}
    for file, content in files.items():
        findings[file] = agent.run(f"Analyze the following code for security vulnerabilities: {content}")
    
    refactored_files = {}
    for file, issues in findings.items():
        if issues and issues.lower() not in ["secure", "okay", "ok"]:
            refactored_files[file] = agent.run(f"Refactor the following code based on these issues: {files[file]} \nIssues: {issues}")
    
    github_manager = GitHubManager(repo_path, branch_name)
    pr_link = github_manager.create_pr(refactored_files)
    
    if args.do_send_email.lower() == "true":
        reporter = EmailReporter()
        reporter.send_report(args.receiver_email, findings, pr_link)
    
    logging.info("Process completed successfully.")

if __name__ == "__main__":
    main()