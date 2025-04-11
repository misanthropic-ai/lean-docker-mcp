# Changelog

## [0.2.0] - 2023-06-28
### Added
- Container pooling system to solve Docker rate limiting issues in high-scale environments
- Intelligent #eval handling to execute Lean code that doesn't define a main function
- Debug mode with detailed logging for troubleshooting
- Support for configuring container resource limits via environment variables
- Automatic pool cleanup and container recycling

### Changed
- Enhanced error reporting for better troubleshooting
- Improved Docker availability detection with clear error messages
- More robust handling of Lean execution

### Fixed
- Docker rate limiting issues when running multiple trajectories in parallel
- "unknown declaration 'main'" errors when executing Lean code with #eval expressions
- Connection issues when Docker is unavailable

## [0.1.0] - 2023-06-14
### Added
- Initial release
- Basic Docker container execution for Lean4 code
- Transient and persistent execution modes
- Security validation for Lean code 