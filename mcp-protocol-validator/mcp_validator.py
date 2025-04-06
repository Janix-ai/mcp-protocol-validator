#!/usr/bin/env python3
# Copyright (c) 2025 Scott Wilcox
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
MCP Protocol Validator

A command-line tool and test suite for validating MCP server implementations.
"""

import os
import sys
import json
import click
import subprocess
from pathlib import Path
import pytest
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

# Initialize rich console for better output
console = Console()

@click.group()
@click.version_option(version="0.1.0")
def cli():
    """MCP Protocol Validator - Test your MCP server implementation."""
    pass

@cli.command()
@click.option("--url", required=True, help="URL of the MCP server to test")
@click.option("--server-command", help="Command to start a local MCP server")
@click.option("--report", default="./mcp-compliance-report.html", help="Path to save the test report")
@click.option("--format", default="html", type=click.Choice(["html", "markdown", "json"]), help="Report format")
@click.option("--test-modules", help="Comma-separated list of test modules to run (base,resources,tools,prompts,utilities)")
def test(url, server_command, report, format, test_modules):
    """Run compliance tests against an MCP server."""
    console.print(f"[bold green]MCP Protocol Validator[/bold green]")
    console.print(f"Testing server at: [bold]{url}[/bold]")
    
    # Start local server if specified
    server_process = None
    if server_command:
        console.print(f"Starting local server: {server_command}")
        server_process = subprocess.Popen(
            server_command, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        # Wait for server to start
        console.print("Waiting for server to start...")
        # TODO: Implement proper wait-for-server logic
    
    try:
        # Set up environment variables for tests
        os.environ["MCP_SERVER_URL"] = url
        
        # Build pytest args
        pytest_args = ["-v"]
        
        # Add report format
        if format == "html":
            pytest_args.extend(["--html", report, "--self-contained-html"])
        
        # Filter test modules if specified
        if test_modules:
            module_list = test_modules.split(",")
            test_paths = []
            if "base" in module_list:
                test_paths.append("tests/test_base_protocol.py")
            if "resources" in module_list:
                test_paths.append("tests/test_resources.py")
            if "tools" in module_list:
                test_paths.append("tests/test_tools.py")
            if "prompts" in module_list:
                test_paths.append("tests/test_prompts.py")
            if "utilities" in module_list:
                test_paths.append("tests/test_utilities.py")
            pytest_args.extend(test_paths)
        else:
            # Run all tests
            pytest_args.append("tests/")
        
        # Run tests
        with Progress() as progress:
            task = progress.add_task("[green]Running tests...", total=100)
            progress.update(task, advance=50)
            
            # Execute pytest
            exit_code = pytest.main(pytest_args)
            
            progress.update(task, completed=100)
        
        # Generate summary
        if os.path.exists(report):
            console.print(f"\n[green]Test report saved to:[/green] {report}")
        
        if exit_code == 0:
            console.print("[bold green]✅ All tests passed![/bold green]")
        else:
            console.print(f"[bold red]❌ Some tests failed (exit code: {exit_code})[/bold red]")
        
    finally:
        # Clean up server process if we started one
        if server_process:
            console.print("Stopping local server...")
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

@cli.command()
def schema():
    """Print the MCP JSON schema."""
    schema_path = Path(__file__).parent / "schema" / "mcp_schema.json"
    if schema_path.exists():
        with open(schema_path) as f:
            schema = json.load(f)
        console.print_json(json.dumps(schema, indent=2))
    else:
        console.print("[bold red]Schema file not found![/bold red]")
        return 1

if __name__ == "__main__":
    cli() 