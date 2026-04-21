"""Patchwright CLI entrypoint. TODO(phase-7): wire up click group."""

import click


@click.command()
@click.argument("prompt", required=False)
def main(prompt: str | None) -> None:
    raise NotImplementedError("cli not yet implemented; see docs/plan.md phase 7")


if __name__ == "__main__":
    main()
