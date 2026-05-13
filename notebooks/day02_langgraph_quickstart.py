from langchain.tools import tool
from langchain.chat_models import init_chat_model
from langchain.messages import AnyMessage
from typing_extensions import TypedDict, Annotated
import operator
from langchain.messages import SystemMessage
from langchain.messages import ToolMessage
from typing import Literal
from langgraph.graph import StateGraph, START, END

# Defin tools and model(예시에서 Claude sonnet 4-6 모델을 사용하여 사칙연산을 위한 도구 정의)

model= init_chat_model(
    "claude-sonnet-4-6",
    temperature=0
)

# Define tools
@tool
def multiply(a: int, b: int) -> int:
    """multiply `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a * b

@tool
def add(a: int, b:int) -> int:
    """Adds `a` and `b`.

    Args:
        a : First int
        b : Second int
    """
    return a + b

@tool
def divide(a: int, b: int) -> float:
    """Divide `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a / b

# Augment the LLM with Tools
tools = [add,multiply,divide]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)

# Define state(그래프의 상태는 메시지와 LLM 호춣 횟수를 저장하는데 사용)
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int

# Define model note(모델 노드는 LLM을 호출하고 도구를 호출할지 여부를 결정하는데 사용)

def llm_call(state: dict):
    """"LLM decides whether to call a tool or not"""

    return{
        "messages": [
            model_with_tools.invoke(
                [
                    SystemMessage(
                        content="You are a helpful assistant tasked with performing arithmetic on a set of inputs"
                    )
                ]
                + state["messages"]
            )

        ],
        "llm_calls" : state.get('llm_calls', 0) + 1 
    }

# Define tool node(툴 노드는 툴을 호출하고 결과를 반환하는데 사용)

def tool_node(state: dict):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}
    
# Define end logic(조건부 에지 함수는 LLM이 툴 호출을 했는지 여부에 따라 툴 노드 또는 끝으로 라우팅하는데 사용)
def should_continue(state: MessagesState) -> Literal["tool_node", END] :
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]

    #if the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"
    
    return END

# Bulid and compile the agent(에이전트는 해당 StateGraph 클래스를 사용하여 구축되고 해당 compile 메서드를 사용하여 컴파일됨)

# Bulid workflow
agent_builder = StateGraph(MessagesState)

# Add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
agent_builder.add_edge("tool_node", "llm_call")

# Compile the agent
agent = agent_builder.compile()

# # Show the agent
# from IPython.display import image, display
# display(Image(agent.get_graph(xray=True).draw_mermaid_png()))

#Invoke
from langchain.messages import HumanMessage
messages = [HumanMessage(content="Add 3 and 4")]
messages = agent.invoke({"messages": messages})
for m in messages["messages"]:
    m.pretty_print()