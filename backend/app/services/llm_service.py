import os
from dotenv import load_dotenv
from colorama import Fore, init
from litellm import completion, Message 

# Initialize colorama for colored terminal output
init(autoreset=True)

# Load API key from .env
load_dotenv()
GEMINI_API_KEY = os.getenv("LLM_API_KEY")

# Define your Agent class here or import it if defined elsewhere
# from .agent import Agent

class Agent:
    def __init__(self, name, model, tools=None, system_prompt="", to_break=None):
        """
        @notice Initializes the Agent class.
        @param model The AI model to be used for generating responses.
        @param tools A list of tools that the agent can use.
        @param available_tools A dictionary of available tools and their corresponding functions.
        @param system_prompt system prompt for agent behaviour.
        """
        self.name = name
        self.model = model
        self.messages = []
        self.tools = tools if tools is not None else []
        self.tools_schemas = self.get_openai_tools_schema() if self.tools else None
        self.system_prompt = system_prompt
        self.to_break = to_break
        if self.system_prompt and not self.messages:
            self.handle_messages_history("system", self.system_prompt)

    def invoke(self, message):
        print(Fore.GREEN + f"\nCalling Agent: {self.name}")
        self.handle_messages_history("user", message)
        result = self.execute()
        return result

    def execute(self):
        """
        @notice Use LLM to generate a response and handle tool calls if needed.
        @return The final response.
        """
        # First, call the AI to get a response
        response_message = self.call_llm()

        # Check if there are tool calls in the response
        tool_calls = response_message.tool_calls

        # If there are tool calls, invoke them
        if tool_calls:
            response_message = self.run_tools(tool_calls)
        
        return response_message.content

    def run_tools(self, tool_calls):
        """
        @notice Runs the necessary tools based on the tool calls from the LLM response.
        @param tool_calls The list of tool calls from the LLM response.
        @return The final response from the LLM after processing tool calls.
        """
        # For each tool the AI wanted to call, call it and add the tool result to the list of messages
        for tool_call in tool_calls:
            output = self.execute_tool(tool_call)

            if self.to_break:
                function_name = tool_call.function.name
                if function_name == self.to_break:
                    if output.startswith('<tool-use>{"tool_calls":[]}</tool-use>'):
                        output = output[len('<tool-use>{"tool_calls":[]}</tool-use>'):]
                        output = output.strip()
                    
                    if output.startswith('---'):
                        output = output[len('---'):]
                        output = output.strip()
                    
                    message = Message(
                        content=output,
                        role="assistant",
                        tool_calls=[],
                        function_call=None,
                        provider_specific_fields=None
                    )

                    return message
            
            

        # Call the AI again so it can produce a response with the result of calling the tool(s)
        response_message = self.call_llm()
        tool_calls = response_message.tool_calls

        # If the AI decided to invoke a tool again, invoke it
        if tool_calls:
            response_message = self.run_tools(tool_calls)

        return response_message

    def execute_tool(self, tool_call):
        """
        @notice Executes a tool based on the tool call from the LLM response.
        @param tool_call The tool call from the LLM response.
        @return The final response from the LLM after executing the tool.
        """
        function_name = tool_call.function.name
        func = next(
            iter([func for func in self.tools if func.__name__ == function_name])
        )

        if not func:
            return f"Error: Function {function_name} not found. Available functions: {[func.__name__ for func in self.tools]}"

        try:
            print(Fore.GREEN + f"\nCalling Tool: {function_name}")
            print(Fore.GREEN + f"Arguments: {tool_call.function.arguments}")
            # init tool
            func = func(**eval(tool_call.function.arguments))
            # get outputs from the tool
            output = func.run()
            
            tool_message = {"name": function_name, "tool_call_id": tool_call.id}
            # print(Fore.GREEN + f"Response: {output}\n")

            self.handle_messages_history("tool", output, tool_output=tool_message)
            return output
        except Exception as e:
            print("Error: ", str(e))
            return "Error: " + str(e)

    def call_llm(self):
        response = completion(
            model=self.model,  # e.g., "gemini/gemini-2.0-flash"
            messages=self.messages,
            tools=self.tools_schemas,
            temperature=0.1,
            api_key=os.getenv("LLM_API_KEY")  # Explicitly pass the Gemini API key
            # No api_base needed for Gemini
        )
        message = response.choices[0].message
        if message.tool_calls is None:
            message.tool_calls = []
        if message.function_call is None:
            message.function_call = {}
        self.handle_messages_history(
            "assistant", message.content, tool_calls=message.tool_calls
        )
        return message

    def reset(self):
        self.messages = []
        if self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})
            
    def get_openai_tools_schema(self):
        return [
            {"type": "function", "function": tool.openai_schema} for tool in self.tools
        ]
            
    def handle_messages_history(self, role, content, tool_calls=None, tool_output=None):
        message = {"role": role, "content": content}
        if tool_calls:
            message["tool_calls"] = self.parse_tool_calls(tool_calls)
        if tool_output:
            message["name"] = tool_output["name"]
            message["tool_call_id"] = tool_output["tool_call_id"]
        # save short-term memory
        self.messages.append(message)

    def parse_tool_calls(self, calls):
        parsed_calls = []
        for call in calls:
            parsed_call = {
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
                "id": call.id,
                "type": call.type,
            }
            parsed_calls.append(parsed_call)
        return parsed_calls
        # ...existing Agent class code...
        pass  # Replace with your full Agent class definition

def process_llm(agent, text_input: str) -> str:
    """
    Calls the Gemini LLM using the provided Agent instance.
    Pass transcribed text and get LLM output.
    """
    response = agent.invoke(text_input)
    return response

global_agent = None

def set_global_agent(agent):
    global global_agent
    global_agent = agent

def get_global_agent():
    return global_agent

