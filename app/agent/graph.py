"""
app.agent.graph — LangGraph state-machine for the AI agent.

Builds the agent graph: Agent Node ←→ Tools Node, compiled and
exposed via the `run_agent()` async entry-point.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import OPENROUTER_API_KEY
from app.agent.tools import (
    # Read tools
    check_pipeline_status,
    check_pending_count,
    check_completed_count,
    check_blocked_feeds,
    # Write tools
    unblock_feed,
    retry_failed_articles,
    purge_failed_articles,
    fetch_open_source_image,
)


# ═══════════════════════════════════════════════════════════════
#  Agent Graph
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    # Read
    check_pipeline_status,
    check_pending_count,
    check_completed_count,
    check_blocked_feeds,
    # Write
    unblock_feed,
    retry_failed_articles,
    purge_failed_articles,
    fetch_open_source_image,
]

SYSTEM_PROMPT = SystemMessage(content=(
    "You are a Senior DevOps AI Assistant for the AI News Scraper pipeline, "
    "communicating with the admin via Telegram. You have full read and write "
    "access to the pipeline through your tools.\n\n"

    "## Your Capabilities\n"
    "You can CHECK the pipeline (article counts by status, blocked feeds) and "
    "you can ACT on it (unblock feeds, retry failed articles, purge failures). "
    "You can also FETCH related open-source images to replace watermarked ones. "
    "Always call a tool to get current data before answering — never guess counts "
    "or reuse stale numbers from earlier in the conversation.\n\n"

    "## Personality\n"
    "You are a knowledgeable, proactive assistant — not a robotic status reader. "
    "Think like a senior engineer helping a colleague. If you spot problems in "
    "the data (high failure rates, blocked feeds), proactively suggest actions. "
    "For example: 'I see 15 failed articles. Want me to retry them or purge them?'\n\n"

    "## Response Style\n"
    "- Keep responses short and scannable for a chat window.\n"
    "- Use status emojis sparingly (✅ ⚠️ ⏳ 🚫) to aid scanning.\n"
    "- When reporting numbers, present them cleanly — don't pad with filler text.\n"
    "- If a tool call fails, report the error plainly.\n\n"

    "## Scope\n"
    "Your primary domain is the news scraper pipeline. You can also help the "
    "admin with general Python, DevOps, and debugging questions using your "
    "own knowledge — you are not limited to only tool-based answers. "
    "If you genuinely don't know something, say so."
))

# LLM — using OpenRouter via the OpenAI-compatible API
llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    model="deepseek/deepseek-chat-v3.1",
    temperature=0.5,
    max_tokens=1000,
)

llm_with_tools = llm.bind_tools(TOOLS)


def agent_node(state: MessagesState):
    """The agent node: prepend system prompt and call the LLM."""
    messages = [SYSTEM_PROMPT] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# Build the graph
graph_builder = StateGraph(MessagesState)
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", ToolNode(TOOLS))

graph_builder.add_edge(START, "agent")
graph_builder.add_conditional_edges("agent", tools_condition)
graph_builder.add_edge("tools", "agent")

# Compile with memory checkpointer for conversation persistence
memory = MemorySaver()
agent_graph = graph_builder.compile(checkpointer=memory)


async def run_agent(user_message: str, thread_id: str = "admin") -> str:
    """
    Run the agent with a user message and return the final text response.
    This is the main entry point called by the Telegram bot.

    The thread_id parameter enables conversation memory — messages within
    the same thread are remembered across invocations.
    """
    config = {"configurable": {"thread_id": thread_id}}
    input_messages = {"messages": [("user", user_message)]}
    result = await agent_graph.ainvoke(input_messages, config=config)

    # The last message in the state is the agent's final response
    final_message = result["messages"][-1]
    return final_message.content
