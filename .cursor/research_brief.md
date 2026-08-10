# Semantic Agent Study - Research Brief

## Project Overview

I want to build an independent research project called **Semantic Agent
Study**.

The goal is to study how different semantic architectures affect the
performance of enterprise AI data agents.

This is not intended to build a production application. It is a
controlled research experiment to evaluate architectural tradeoffs.

------------------------------------------------------------------------

# Motivation

Enterprise AI agents increasingly rely on semantic layers to translate
natural language business questions into data queries.

There are two competing architectural approaches:

## Approach 1: Unified Semantic Model

A single semantic model contains all relevant business entities,
metrics, relationships, and definitions.

The assumption: - LLMs can reason across domains when provided
sufficient context. - Business questions often do not align with
database boundaries.

Potential advantages: - better cross-domain reasoning - fewer routing
failures - better support for open-ended executive/business questions

Potential disadvantages: - more ambiguity - larger context - harder
evaluation

------------------------------------------------------------------------

## Approach 2: Decomposed Semantic Models

Multiple smaller semantic models represent specialized domains.

Example domains: - deposits - lending - customers - market intelligence

The assumption: - smaller contexts improve reliability. - specialized
agents are easier to evaluate and optimize.

Potential advantages: - better precision - easier debugging - simpler
evaluation

Potential disadvantages: - routing failures - inability to answer
cross-domain questions - coordination complexity

------------------------------------------------------------------------

# Research Question

When does semantic decomposition improve enterprise AI agent
performance, and when does it reduce the ability to answer complex
business questions?

The research should not assume either approach is superior.

The goal is to identify the tradeoffs.

------------------------------------------------------------------------

# Hypotheses

## H1: Specialized models improve bounded analytical tasks

Decomposed semantic models should perform better on narrow questions
with clear domain boundaries.

Example:

"What was mortgage origination volume last quarter?"

## H2: Unified models improve cross-domain reasoning

Unified semantic models should perform better on questions requiring
multiple business domains.

Example:

"Which customer segments are reducing deposits and increasing borrowing
behavior?"

## H3: Routing introduces new failure modes

Examples: - wrong domain selection - failure to invoke required tools -
incomplete answers - inability to synthesize across domains

------------------------------------------------------------------------

# Dataset

Use public datasets available through my Snowflake account.

The dataset should represent a realistic enterprise banking analytics
environment.

Potential domains: - customers - accounts - deposits - transactions -
lending - mortgages - branches - geographic markets - competitor
information - economic indicators

The same underlying data should be used for all experiments.

The only variable should be the semantic architecture.

------------------------------------------------------------------------

# Experimental Design

## Experiment A: Unified Semantic Agent

Flow:

User question\
→ LLM agent\
→ unified YAML semantic model\
→ SQL generation\
→ database query\
→ answer

The agent has access to the complete semantic model.

## Experiment B: Routed Semantic Agents

Flow:

User question\
→ router\
→ specialist agent\
→ domain YAML semantic model\
→ SQL generation\
→ answer

The system should log: - routing decision - selected domain - generated
SQL - final answer - failure modes

# Evaluation Framework

Avoid overfitting to simple questions.

The benchmark should include realistic enterprise workflows.

## Category 1: Single-domain analytical questions

Examples: - "What is total mortgage volume by state?" - "What was
deposit growth last quarter?"

Measure: - SQL correctness - factual accuracy

## Category 2: Cross-domain analytical questions

Examples: - "Which customer segments are most likely to move deposits to
competitors?"

Requires: - customer data - deposits - transactions - market data

Measure: - domain coverage - tool selection - reasoning quality

## Category 3: Executive decision questions

Examples: - "Give me a competitive landscape analysis for Evansville for
deposits and lending."

Measure: - completeness - synthesis quality - business usefulness

------------------------------------------------------------------------

# Metrics

Track:

## Semantic accuracy

Did the agent select the correct entities, metrics, and relationships?

## SQL correctness

Did the generated query correctly answer the question?

## Tool/domain selection accuracy

Especially important for routed systems.

## Cross-domain completion rate

Percentage of multi-domain questions successfully answered.

## Answer quality

Human evaluation: - correctness - completeness - usefulness

## Evaluation complexity

Measure maintenance cost: - number of evaluation cases - routing tests -
domain interaction tests

------------------------------------------------------------------------

# Technical Requirements

This should be a research prototype.

Prioritize: - simplicity - reproducibility - experiment clarity -
logging

Avoid: - production UI - unnecessary infrastructure - complex agent
frameworks

Preferred stack: - Python - Snowflake connector - YAML
semantic models - LLM API - lightweight agent implementation

------------------------------------------------------------------------

# Development Plan Requested

Before writing code, generate a plan covering:

1.  Repository structure
2.  System architecture
3.  Data ingestion strategy
4.  Semantic model representation
5.  Agent implementation design
6.  Evaluation framework
7.  Experiment workflow
8.  Milestones
9.  Risks and open questions

Act as a research engineer. Challenge assumptions, identify confounders,
and prioritize experimental validity over implementation complexity.
