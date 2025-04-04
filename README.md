# MCP Protocol Validator

A comprehensive testing tool for validating Model Context Protocol (MCP) server and client implementations.

## Overview

The MCP Protocol Validator is a containerized test suite designed to ensure compliance with the Model Context Protocol specification. It provides:

- **Comprehensive Tests**: Verifies all essential aspects of the MCP specification
- **Easy Setup**: Run with a single command using Docker
- **Detailed Reports**: Generate HTML or JSON reports for compliance analysis
- **CI Integration**: GitHub Action for continuous validation
- **Weighted Compliance Scoring**: Prioritizes critical requirements for accurate compliance assessment

## Features

- **Base Protocol Tests**: Initialization, capabilities, JSON-RPC compliance
- **Resources Tests**: List and read operations for resources
- **Tools Tests**: Discovery and invocation of tools
- **Prompts Tests**: Listing and retrieval of prompts
- **Utilities Tests**: Ping, cancellation, progress, logging, and more
- **Client Tests**: Roots and sampling features

## Installation

### Using Docker (Recommended)

```bash
docker pull yourorg/mcp-protocol-validator:latest
```

### From Source

```bash
git clone https://github.com/your-org/mcp-protocol-validator.git
cd mcp-protocol-validator

# Install dependencies
pip install -r mcp-protocol-validator/requirements.txt
```

## Usage

### Command Line

Test an MCP server using Docker:

```bash
docker run --rm yourorg/mcp-protocol-validator:latest \
  --url https://your-mcp-server.com/mcp \
  --report ./reports/compliance-report.html
```

Test specific modules:

```bash
docker run --rm yourorg/mcp-protocol-validator:latest \
  --url https://your-mcp-server.com/mcp \
  --test-modules base,resources,tools \
  --report ./reports/compliance-report.html
```

### Local Development

```bash
# Test a local server
cd mcp-protocol-validator
python mcp_validator.py test \
  --url http://localhost:8080 \
  --report ./compliance-report.html
```

### GitHub Actions Integration

Add the following to your workflow file:

```yaml
- name: Run MCP Compliance Tests
  uses: yourorg/mcp-protocol-validator-action@v1
  with:
    server-url: http://localhost:8080
    test-modules: base,resources,tools,prompts,utilities
```

## Testing Clients

To test MCP clients:

```bash
# Set environment variables for client testing
export MCP_CLIENT_URL=http://localhost:8766
export MOCK_MCP_SERVER=1

# Run client tests
cd mcp-protocol-validator
python -m pytest tests/test_roots.py tests/test_sampling.py -v
```

## Compliance Scoring System

The validator uses a weighted scoring system to accurately reflect the importance of different requirements:

| Requirement Level | Weight | Impact | Severity |
|-------------------|--------|--------|----------|
| MUST (M-prefixed) | 10 | 80% | 🔴 Critical |
| SHOULD (S-prefixed) | 3 | 15% | 🟠 Medium |
| MAY (A-prefixed) | 1 | 5% | 🟢 Low |

This weighting ensures that failing critical requirements has a significantly larger impact on the compliance score than failing optional ones. The overall compliance score is calculated using:

```
ComplianceScore = (10*MustPassed + 3*ShouldPassed + 1*MayPassed) / (10*TotalMust + 3*TotalShould + 1*TotalMay) * 100
```

Based on the calculated score, implementations are classified into one of these compliance levels:

- **Fully Compliant** (100%): Passes all MUST requirements
- **Substantially Compliant** (90-99%): Passes most MUST requirements with minor issues
- **Partially Compliant** (75-89%): Has significant compliance issues
- **Minimally Compliant** (50-74%): Major interoperability concerns
- **Non-Compliant** (<50%): Unlikely to be interoperable

For more details, see [Compliance Scoring](docs/compliance-scoring.md).

## Reports

Reports are generated in the format specified by the `--format` option:

- **HTML**: Interactive report with detailed test results
- **Markdown**: Simple text-based report
- **JSON**: Structured data for programmatic analysis

Each report includes:
- Overall compliance score and level
- Breakdown by requirement type (MUST, SHOULD, MAY)
- Section-by-section compliance details
- Failed tests categorized by severity
- Prioritized remediation plan
- Performance metrics (where available)

See a [sample report](docs/updated-sample-report.md) for an example.

## Development

### Running Tests

```bash
cd mcp-protocol-validator
python -m pytest
```

### Building the Docker Image

```bash
cd mcp-protocol-validator
docker build -t mcp-protocol-validator .
```

## Specification Compliance

The test suite is based on the Model Context Protocol specification version 2025-03-26 and covers:

- **MUST** requirements: Essential for compliance (89 requirements)
- **SHOULD** requirements: Recommended practices (30 requirements)
- **MAY** requirements: Optional features (26 requirements)

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 