from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from local_llm.agent.state import AgentState
from local_llm.tools.registry import perform_web_search, perform_web_fetch


def agent_node(state: AgentState) -> Dict[str, Any]:
    """
    Reasoning / Decision node in LangGraph ReAct flow.
    """
    return state


def tool_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes all intercepted tool calls in parallel or sequence.
    """
    tool_calls = state.get("tool_calls", [])
    results: List[Dict[str, Any]] = []

    for call in tool_calls:
        tool_name = call.get("tool_name")
        args = call.get("args", {})
        call_id = call.get("tool_call_id")

        if tool_name == "web_search":
            query = args.get("query", "")
            raw_res = perform_web_search(query)
            results.append({
                "tool_name": tool_name,
                "tool_call_id": call_id,
                "args": args,
                "result": raw_res
            })
        elif tool_name == "web_fetch":
            url = args.get("url", "")
            raw_res = perform_web_fetch(url)
            results.append({
                "tool_name": tool_name,
                "tool_call_id": call_id,
                "args": args,
                "result": raw_res
            })

    return {"tool_results": results}


def should_continue(state: AgentState) -> str:
    """
    Determines whether to route to tools execution node or terminate.
    """
    if state.get("tool_calls"):
        return "tools"
    return END


def build_react_graph():
    """
    Builds and compiles the LangGraph StateGraph ReAct agent.
    """
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()


react_graph = build_react_graph()
