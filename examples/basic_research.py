#!/usr/bin/env python3
"""
Basic Research Cycle Example

Demonstrates running a complete Tinman research cycle to discover
failure modes in an AI system.

Usage:
    export OPENAI_API_KEY="sk-..."
    python examples/basic_research.py
"""

import asyncio
import os

from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient, AnthropicClient


async def main():
    # Choose your model provider
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        print("Using OpenAI...")
        client = OpenAIClient(api_key=api_key)
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            print("Using Anthropic...")
            client = AnthropicClient(api_key=api_key)
        else:
            print("Error: Set OPENAI_API_KEY or ANTHROPIC_API_KEY")
            return

    # Create Tinman instance
    # Use skip_db=True for quick testing without PostgreSQL
    print("\nInitializing Tinman in LAB mode...")
    tinman = await create_tinman(
        mode=OperatingMode.LAB,
        model_client=client,
        skip_db=True,  # Set to False and provide db_url for persistence
    )

    print("Tinman initialized successfully!")
    print(f"State: {tinman.get_state()}\n")

    # Run a research cycle
    print("=" * 60)
    print("Starting Research Cycle")
    print("=" * 60)
    print("\nFocus: Reasoning failures in code generation\n")

    results = await tinman.research_cycle(
        focus="reasoning failures in code generation",
        max_hypotheses=3,       # Number of hypotheses to generate
        max_experiments=2,      # Experiments per hypothesis
        runs_per_experiment=3,  # Runs per experiment
    )

    # Display results
    print("\n" + "=" * 60)
    print("Research Cycle Results")
    print("=" * 60)

    print(f"\nHypotheses generated: {len(results['hypotheses'])}")
    for i, h in enumerate(results['hypotheses'], 1):
        print(f"  {i}. {h.get('target_surface', 'Unknown')} - "
              f"{h.get('expected_failure', 'Unknown')[:50]}...")

    print(f"\nExperiments designed: {len(results['experiments'])}")
    for i, e in enumerate(results['experiments'], 1):
        print(f"  {i}. {e.get('name', 'Unknown')} ({e.get('stress_type', 'Unknown')})")

    print(f"\nFailures discovered: {len(results['failures'])}")
    for i, f in enumerate(results['failures'], 1):
        print(f"  {i}. [{f.get('severity', 'Unknown')}] "
              f"{f.get('primary_class', 'Unknown')}: "
              f"{f.get('description', 'Unknown')[:50]}...")

    print(f"\nInterventions proposed: {len(results['interventions'])}")
    for i, intervention in enumerate(results['interventions'], 1):
        print(f"  {i}. {intervention.get('name', 'Unknown')} "
              f"({intervention.get('type', 'Unknown')})")

    # Generate a report
    print("\n" + "=" * 60)
    print("Generating Report")
    print("=" * 60)

    report = await tinman.generate_report(format="markdown")
    print("\n" + report[:2000] + "..." if len(report) > 2000 else "\n" + report)

    # Get suggestions for next steps
    print("\n" + "=" * 60)
    print("Next Steps")
    print("=" * 60)

    suggestions = await tinman.suggest_next_steps()
    for i, suggestion in enumerate(suggestions, 1):
        print(f"  {i}. {suggestion}")

    # Cleanup
    await tinman.close()
    print("\n\nResearch cycle complete!")


if __name__ == "__main__":
    asyncio.run(main())
