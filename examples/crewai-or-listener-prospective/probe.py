from __future__ import annotations

import asyncio
import json

from crewai.flow.flow import Flow, listen, or_, start


PREFIX = "PROOFDIFF_PROBE="


def run_probe() -> dict[str, object]:
    state: dict[str, object] = {"completed": [], "joined": 0}

    class ParallelFanoutOrFlow(Flow):
        @start()
        def begin(self) -> str:
            return "begin"

        @listen(begin)
        async def fast_branch(self) -> None:
            await asyncio.sleep(0)
            completed = state["completed"]
            assert isinstance(completed, list)
            completed.append("fast")

        @listen(begin)
        async def slow_branch(self) -> None:
            await asyncio.sleep(0.05)
            completed = state["completed"]
            assert isinstance(completed, list)
            completed.append("slow")

        @listen(or_(fast_branch, slow_branch))
        def join(self) -> None:
            joined = state["joined"]
            assert isinstance(joined, int)
            state["joined"] = joined + 1

    runtime_error: str | None = None
    try:
        asyncio.run(ParallelFanoutOrFlow().kickoff_async())
    except BaseException as exc:  # capture the runtime behavior without hiding it
        runtime_error = f"{type(exc).__name__}: {exc}"

    completed = state["completed"]
    joined = state["joined"]
    assert isinstance(completed, list)
    assert isinstance(joined, int)
    return {
        "completed": completed,
        "joined": joined,
        "runtime_error": runtime_error,
    }


def main() -> int:
    print(PREFIX + json.dumps(run_probe(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
