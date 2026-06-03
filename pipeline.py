from agents import architect, deployer, developer, tester
from shared_context import SharedContext


def run_pipeline(user_input: str) -> SharedContext:
    context = SharedContext(user_input=user_input)
    context.log("Pipeline started")

    for agent_module, agent_num in [
        (architect, 1),
        (developer, 2),
        (tester, 3),
        (deployer, 4),
    ]:
        context.pipeline_status[f"agent_{agent_num}"] = "working"
        context.current_agent = agent_num
        try:
            agent_module.run(context)
        except Exception as exc:
            context.pipeline_status[f"agent_{agent_num}"] = "error"
            context.log(f"Agent {agent_num} failed: {exc}")
            break

    context.log("Pipeline complete")
    return context


if __name__ == "__main__":
    user_description = input("Describe the app you want to build: ")
    result = run_pipeline(user_description)
    print("\nDone. Check ./output/ for all generated files.")
    print("Quality report: ./output/tests/quality_report.md")
