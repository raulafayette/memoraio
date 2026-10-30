---
title: "Memoraio: help build a local audiovisual library that remembers where you left off"
tags: opensource, showdev, python, productivity
published: false
---

Following audiovisual content over time creates an organization problem: links accumulate, files get downloaded twice, and it becomes difficult to tell what is already stored, what is new, or where a transcript was saved.

We are opening **Memoraio** to contributors to make this workflow easier to understand and maintain.

## What the app does

Memoraio keeps a local catalog of channels and files. Each channel has its own status, queue and controls. Refreshing an inventory is separate from starting a download. Users explicitly start one channel, a selection or all channels; the service can distribute work across up to three channels in parallel.

The interface separates active work, waiting jobs, paused channels and completed batches. Existing valid files are checked so a recurring visit can continue from the current library. TXT copies are organized by channel and completion month.

Transcripts and media downloads have separate workflows. The current YouTube transcription workflow retrieves available captions without downloading a complete video just to produce text. MP3 and MP4 downloads have their own queue. Speech recognition for Instagram is an optional, separately configured local feature on Apple Silicon.

## Current status and limits

The main application has a native AppKit/WebKit shell for Apple Silicon Macs and a local Python service. Windows currently has an experimental WSL 2 edition with a browser interface. A native Windows client is roadmap work.

The source includes tests for queue control, recovery, file integrity and publication privacy. These tests do not certify universal platform access or transcription quality. Content access can be restricted, and some videos have no available captions.

The public demonstration uses a disposable catalog, fictional sources and clearly labeled simulated progress. It does not contain a user's library, channel list or real transcripts.

## Five concrete ways to help

1. [Validate first-time Windows/WSL installation](https://github.com/raulafayette/memoraio/issues/1): run the documented steps on a clean Windows test account and report reproducible results.
2. [Audit keyboard navigation](https://github.com/raulafayette/memoraio/issues/2): reproduce one focus or accessible-name barrier and propose a small fix.
3. [Review English onboarding](https://github.com/raulafayette/memoraio/issues/3): improve terminology and instructions for someone new to the project.
4. [Expand interruption/recovery coverage](https://github.com/raulafayette/memoraio/issues/4): identify a missing contract and prove it with a disposable, deterministic regression test.
5. [Improve one step of Mac installation](https://github.com/raulafayette/memoraio/issues/5): document clean-install friction and improve a preflight check, message or instruction.

Testing and documentation are useful contributions even if you do not write application code. Each issue includes scope and completion criteria. Small changes with clear verification are welcome.

## Try it or choose a task

- [Project and overview](https://github.com/raulafayette/memoraio)
- [Contributor guide in Portuguese and English](https://github.com/raulafayette/memoraio/blob/main/CONTRIBUTING.md)
- [Synthetic demonstration](https://github.com/raulafayette/memoraio/blob/main/docs/demo.md)
- [Collaborative roadmap](https://github.com/raulafayette/memoraio/blob/main/docs/ROADMAP.md)

If you recognize this problem in your own workflow, we would appreciate a specific account of where the app helps or gets in the way. Please use fictional examples and sanitized diagnostics; personal libraries, cookies and real transcripts do not belong in public reports.
