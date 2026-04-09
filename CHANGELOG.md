# Changelog

## [0.2.0] - 2026-04-08

### Added

- add report command and improve collect-all progress tracking (#58)
- add --help-agent flag for AI-friendly CLI reference (#48)
- add structured logging for collection runs with JSONL output (#45)
- auto-detect version bump type from conventional commits (#43)
- add document search with local and provider support (#42)
- add terminal padding and move manual to its own page (#34)
- integrate man pages into website as interactive documentation section (#33)
- add GitHub Pages website with data extraction from source (#27)
- add PyPI deployment action and release pipeline (#25)
- add e2e tests, parsing rules document, and fix summary threshold inconsistency (#21)
- add retry logic, validation, tests, progress bar, and concurrent collection (#20)
- add manpages for all commands, accessible via "juris man <command>" (#18)
- add collect-all command with deduplicated provider selection (#17)
- add EU law collectors (EUR-Lex, CJEU, ECtHR) (#11)
- add myndighetsföreskrifter collector (AFS, SOSFS/HSLF-FS) (#10)
- add JO/JK decisions collector (#9)
- add HFD, MÖD, and PMÖD court types to domstol collector (#8)
- add support for Arbetsdomstolen (AD) court decisions (#7)
- add court scraping support for Högsta domstolens prejudikat (#5)
- add sfs support to RiksdagenCollector (#4)
- add Regeringen.se scraper for Swedish förarbeten (#3)
- add Swedish legal data collection framework (#1)

### Fixed

- use retry logic in Riksdagen API requests and track completeness (#60)
- prevent duplicate document collection in regeringen collector (#47)
- add DS designation extraction and auto-incremental collection (#46)
- trigger release workflow from version-bump via workflow_dispatch (#44)
- respect limit during JK/JO discovery phase and add progress logging (#41)
- add run target to Makefile for executing juris CLI (#40)
- migrate JK collector from listing pages to POST-based search (#39)
- handle Riksdagen API reclassification of SKR documents (#38)
- lock width on mobile to prevent horizontal scroll (#36)
- add basename to BrowserRouter for GitHub Pages routing (#35)
- remove deprecated mix_stderr parameter from CliRunner (#32)
- resolve all 36 mypy strict mode errors (#31)
- add pytest-timeout to dev dependencies (#30)
- ensure data directory exists before writing sourceData.ts (#28)
- move dependencies from [project.urls] to [project] section (#26)
- harmonize output quality across all collectors (#19)
- harmonize document quality across all 8 collectors (#16)

### Changed

- auto-discovery provider registry and pipeline extraction (#24)
- harmonize collectors and fix inconsistencies across codebase (#14)
- PDF download/extraction to base collector and add skip_content flag (#13)

### Documentation

- add OSS community files and GitHub templates (#49)
- add comprehensive code documentation and integrate into website (#37)
- add CLAUDE.md with project structure, summary, and dev process (#22)
- expand README with comprehensive documentation and usage examples (#12)
- add issues for missing legal sources in rättskällehierarkin (#6)
- add readme (#2)

All notable changes to this project will be documented in this file.

This changelog is automatically generated from [conventional commits](https://www.conventionalcommits.org/) during the release process.
