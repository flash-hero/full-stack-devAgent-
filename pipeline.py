from agents import architect, deployer, developer, tester
from shared_context import SharedContext


def run_pipeline(user_input: str, context: SharedContext | None = None) -> SharedContext:
    context = context or SharedContext(user_input=user_input)
    context.log("Pipeline started")

    for agent_module, agent_num in [
        (architect, 1),
        (developer, 2),
        (tester, 3),
        (deployer, 4),
    ]:
        agent_key = f"agent_{agent_num}"
        context.pipeline_status[agent_key] = "working"
        context.current_agent = agent_num
        try:
            agent_module.run(context)
        except Exception as exc:
            context.pipeline_status[agent_key] = "error"
            context.log(f"Agent {agent_num} failed: {exc}")
            break
        if context.pipeline_status.get(agent_key) == "working":
            context.pipeline_status[agent_key] = "done"

    context.log("Pipeline complete")
    if "error" not in context.pipeline_status.values():
        context.current_agent = 0
    return context


if __name__ == "__main__":
    user_description = input("Describe the app you want to build: ")
    result = run_pipeline(user_description)
    print("\nDone. Check ./output/ for all generated files.")
    print("Quality report: ./output/tests/quality_report.md")
