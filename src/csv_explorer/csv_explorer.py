import os
import ast
import uuid
from importlib import import_module
from typing import Any, Optional

import matplotlib.pyplot as plt
from langchain.memory.buffer_window import ConversationBufferWindowMemory
from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool
from langchain_experimental.agents.agent_toolkits import create_csv_agent
import csv_explorer

TOOLS_FILEPATH = os.path.join("/".join(os.path.abspath(csv_explorer.__file__).split("/")[:-1]), "tools.py")

TEMP_FILEPATH = "/tmp"

AGENTS = [
    "chat-conversational-react-description",
    "chat-zero-shot-react-description",
    "conversational-react-description",
    "openai-functions",
    "openai-tools",
    "openai-multi-functions",
    "react-docstore",
    "self-ask-with-search",
    "structured-chat-zero-shot-react-description",
    "zero-shot-react-description",
]


LLM_MODELS = {
    "gpt-3.5-turbo": ChatOpenAI,
}


class CSVExplorer:
    """
    A class for exploring CSV files using AI-powered tools.

    Args:
        filepath (str): The path to the CSV file.
        extra_tools (list[StructuredTool], optional): Additional tools to use for exploration. Defaults to an empty list.
        agent_type (str, optional): The type of AI agent to use. Defaults to "openai-tools".
        model (str, optional): The AI model to use. Defaults to "gpt-3.5-turbo".
        temperature (float, optional): The temperature parameter for generating AI responses. Defaults to 0.
        memory_k (int, optional): The number of previous conversation turns to consider for context. Defaults to 3.
    """

    tools_filepath: str = TOOLS_FILEPATH
    temp_filepath: str = TEMP_FILEPATH
    _instance = None

    def __init__(
        self,
        filepath: str,
        extra_tools: list[StructuredTool] = [],
        agent_type: str = "openai-functions",
        model: str = "gpt-3.5-turbo",
        temperature: float = 0,
        memory_k: int = 3,
    ):
        self._set_temp_folder()
        self.filepath = filepath
        self.tools = self._set_tools(extra_tools)
        self.agent_type = self._set_agent_type(agent_type)
        self.model = self._set_model(model)
        self.temperature = temperature
        self.memory_k = memory_k
        self.llm = self._set_llm()
        self.memory = self._set_memory()
        self.agent = create_csv_agent(
            self.llm,
            self.filepath,
            verbose=True,
            agent_type=self.agent_type,
            extra_tools=self.tools,
            return_intermediate_steps=True,
        )

    def invoke(self, query):
        """
        Invokes the AI agent with a query and returns the response.

        Args:
            query (str): The query to send to the AI agent.

        Returns:
            str: The response from the AI agent.
        """

        prompt = (
            "# Histórico de conversa\n"
            f"{self.memory.buffer_as_str}\n{self.memory.human_prefix}: {query}\n\n"
            "# Instruções\n"
            f"- Leia os dados do csv '{self.filepath}'.\n"
            "- NÃO use `python_repl_ast` para gerar plots. Se precisar gerar plots, use a tool `plot_generator`. "
            "Quando for pasar o código de matplotlib para a ferramenta, não esqueça de passar a instrucao `plt.show()`"

        )
        answer = self.agent.invoke(prompt)

        response = self._update_memory(answer)

        # fig = plt.gcf()
        # if fig:
        #     return fig

        # response = self._update_memory(answer)
        return response

    @classmethod
    def get_tools(cls) -> list[StructuredTool]:
        """
        Retrieves a list of structured tools from the CSVExplorer tools file.

        Returns:
            A list of StructuredTool objects representing the available tools.
        """
        module = "csv_explorer.tools"
        decorator_name = "tool"

        with open(CSVExplorer.tools_filepath, "r") as file:
            tree = ast.parse(file.read(), filename=CSVExplorer.tools_filepath)

        functions_with_decorator = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Name) and decorator.id == decorator_name
        ]

        return [_import_function(module, f) for f in functions_with_decorator]

    @classmethod
    def list_agents():
        """
        Returns a list of available AI agents.

        Returns:
            list: A list of available AI agents.
        """
        return AGENTS

    @classmethod
    def list_llm_models():
        """
        Returns a list of available language models for the AI agent.

        Returns:
            list: A list of available language models.
        """
        return list(LLM_MODELS.keys())

    def _set_model(self, model: str) -> Any:
        if model not in LLM_MODELS:
            raise LLMModelNotRecognized()
        return model

    def _set_llm(self) -> Any:
        return LLM_MODELS[self.model](
            model=self.model, temperature=self.temperature, verbose=True
        )

    def _set_tools(self, extra_tools: str) -> str:
        return CSVExplorer.get_tools() + extra_tools

    def _set_agent_type(self, agent_type: str) -> str:
        if agent_type not in AGENTS:
            raise AgentTypeNotRecognized()
        return agent_type

    def _set_memory(self):
        memory = ConversationBufferWindowMemory(k=self.memory_k)
        memory.save_context({"input": "Olá!"}, {"output": "Olá!. Como posso ajudar?"})
        return memory

    def _update_memory(self, answer):

        fig = plt.gcf()
        if fig:

            plots = [
                (action, result)
                for action, result in answer["intermediate_steps"]
                if action.tool == 'plot_generator'
            ]

            if len(plots) > 0:
                self.memory.save_context(
                    {"input": answer["input"]}, {"output": str(plots[-1][0].tool_input['plot_description'])}
                )

            return fig

        else:
            self.memory.save_context(
                {"input": answer["input"]}, {"output": answer["output"]}
            )

            return answer["output"]


    @classmethod
    def _set_temp_folder(cls):
        _create_directory_if_not_exists(cls.temp_filepath)


def _create_directory_if_not_exists(folderpath):
    if not os.path.exists(folderpath):
        os.makedirs(folderpath)


def _import_function(module_name: str, function_name: str) -> Optional[Any]:
    """
    Importa uma função de um módulo e retorna a função.

    Args:
        module_name (str): O nome do módulo a ser importado.
        function_name (str): O nome da função a ser obtida do módulo.

    Returns:
        Optional[Any]: A função importada, se encontrada. Caso contrário, retorna None.
    """
    try:
        module = import_module(module_name)
        function = getattr(module, function_name)
        return function
    except ImportError:
        print(f"Módulo {module_name} não encontrado.")
    except AttributeError:
        print(f"Função {function_name} não encontrada no módulo {module_name}.")


def _has_content(fig):
    has_content = False
    for ax in fig.axes:
        if ax.lines or ax.patches or ax.texts or ax.images or ax.collections:
            has_content = True
            break
    return has_content

class AgentTypeNotRecognized(Exception):
    pass


class LLMModelNotRecognized(Exception):
    pass