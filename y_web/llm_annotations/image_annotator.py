import autogen
from autogen.agentchat.contrib.multimodal_conversable_agent import (
    MultimodalConversableAgent,
)


class Annotator(object):
    def __init__(self, llmv):
        self.config_list = [
            {
                "model": llmv,
                "base_url": "http://127.0.0.1:11434/v1",
                "timeout": 10000,
                "api_type": "open_ai",
                "api_key": "NULL",
                "price": [0, 0],
            }
        ]

        self.image_agent = MultimodalConversableAgent(
            name="image-explainer",
            max_consecutive_auto_reply=1,
            llm_config={
                "config_list": self.config_list,
                "temperature": 0.5,
                "max_tokens": 300,
            },
            human_input_mode="NEVER",
        )

        self.user_proxy = autogen.AssistantAgent(
            name="User_proxy",
            max_consecutive_auto_reply=0,
        )

    def annotate(self, image):
        self.user_proxy.initiate_chat(
            self.image_agent,
            silent=True,
            message=f"""Describe the following image. 
            Write in english. <img {image}>""",
        )

        res = self.image_agent.chat_messages[self.user_proxy][-1]["content"][-1]["text"]

        if "I'm sorry" in res:
            res = None
        return res
