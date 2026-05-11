import sys
import asyncio
from pathlib import Path

# Load .env from project root before anything else imports Config
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

from orchestrator import OperatorCore
from config import Config
from logger_config import op_logger


def run():
    is_valid, warnings = Config.validate_config()

    if warnings:
        print("Configuration warnings:")
        for w in warnings:
            print(f"  {w}")
        print()

    if not is_valid:
        print("Configuration invalid. Set MISTRAL_API_KEY or GEMINI_API_KEY environment variables.")
        return 1

    op_logger.header("OPERATOR STARTING")
    operator = OperatorCore(provider_name=Config.DEFAULT_AI_PROVIDER)
    op_logger.success("Ready")

    print()
    print("=" * 60)
    print("OPERATOR - AI Terminal Assistant")
    print("=" * 60)
    print("Type /help for available commands, /exit to quit.")
    print()

    while True:
        try:
            user_input = input("OPERATOR> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                print("Goodbye!")
                break

            print()
            result = asyncio.run(operator.process_task(user_input))
            print(result.message)

            if not result.success:
                print("\nTask completed with errors.")

        except KeyboardInterrupt:
            print("\nInterrupted. Goodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(run())
