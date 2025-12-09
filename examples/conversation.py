#!/usr/bin/env python3
"""
Conversation Example

Demonstrates having an interactive dialogue with Tinman
to discuss research findings and get recommendations.

Usage:
    export OPENAI_API_KEY="sk-..."
    python examples/conversation.py
"""

import asyncio
import os

from tinman import create_tinman, OperatingMode
from tinman.integrations import OpenAIClient, AnthropicClient


async def main():
    # Set up model client
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

    # Initialize Tinman
    print("\nInitializing Tinman...")
    tinman = await create_tinman(
        mode=OperatingMode.LAB,
        model_client=client,
        skip_db=True,
    )
    print("Ready!\n")

    print("=" * 60)
    print("Tinman Conversation Mode")
    print("=" * 60)
    print("""
You can ask Tinman questions about:
- AI failure modes and patterns
- Research recommendations
- Interpretation of findings
- Strategic directions

Commands:
  /research    - Run a quick research cycle
  /report      - Generate a report
  /suggestions - Get research suggestions
  /state       - Show current state
  /reset       - Reset conversation
  /quit        - Exit

""")

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                cmd = user_input[1:].lower().split()[0]

                if cmd == "quit" or cmd == "exit":
                    print("\nGoodbye!")
                    break

                elif cmd == "research":
                    print("\nRunning research cycle...")
                    results = await tinman.research_cycle(
                        max_hypotheses=3,
                        max_experiments=2,
                    )
                    print(f"\nResults:")
                    print(f"  Hypotheses: {len(results['hypotheses'])}")
                    print(f"  Experiments: {len(results['experiments'])}")
                    print(f"  Failures: {len(results['failures'])}")
                    print(f"  Interventions: {len(results['interventions'])}")
                    print()
                    continue

                elif cmd == "report":
                    print("\nGenerating report...")
                    report = await tinman.generate_report()
                    print("\n" + "-" * 40)
                    print(report[:3000] + "..." if len(report) > 3000 else report)
                    print("-" * 40 + "\n")
                    continue

                elif cmd == "suggestions":
                    print("\nGetting research suggestions...")
                    suggestions = await tinman.suggest_next_steps()
                    print("\nNext steps to consider:")
                    for i, s in enumerate(suggestions, 1):
                        print(f"  {i}. {s}")
                    print()
                    continue

                elif cmd == "state":
                    state = tinman.get_state()
                    print(f"\nCurrent state:")
                    for key, value in state.items():
                        print(f"  {key}: {value}")
                    print()
                    continue

                elif cmd == "reset":
                    tinman.reset_conversation()
                    print("\nConversation reset.\n")
                    continue

                else:
                    print(f"\nUnknown command: {cmd}")
                    print("Available: /research, /report, /suggestions, /state, /reset, /quit\n")
                    continue

            # Have a conversation
            print("\nTinman: ", end="", flush=True)
            response = await tinman.discuss(user_input)
            print(response)
            print()

        except KeyboardInterrupt:
            print("\n\nInterrupted. Use /quit to exit.")
        except Exception as e:
            print(f"\nError: {e}")
            print("Try again or use /quit to exit.\n")

    # Cleanup
    await tinman.close()


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║                 Tinman Conversation Demo                 ║
║                                                          ║
║  An interactive dialogue with your AI research assistant ║
╚══════════════════════════════════════════════════════════╝
""")
    asyncio.run(main())
