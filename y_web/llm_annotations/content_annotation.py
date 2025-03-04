from autogen import AssistantAgent
import re


class ContentAnnotator(object):
    def __init__(self, llm=None):
        """
        Initialize the content annotator.

        :param config:
        """

        if llm is not None:
            self.config_list = [
                {
                    "model": llm,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "timeout": 10000,
                    "api_type": "open_ai",
                    "api_key": "NULL",
                    "price": [0, 0],
                }
            ]

            self.annotator = AssistantAgent(
                name=f"Annotator",
                llm_config={
                    "config_list": self.config_list,
                    "temperature": 0,
                    "max_tokens": -1,
                },
                system_message="You are a clever and efficient text annotator. Act as specified by the Handler.",
                max_consecutive_auto_reply=1,
            )

            self.handler = AssistantAgent(
                name=f"Handler",
                llm_config={
                    "config_list": self.config_list,
                    "temperature": 0,
                    "max_tokens": -1,
                },
                system_message="You are the Handler which provides task details to the annotator.",
                max_consecutive_auto_reply=0,
            )
        else:
            self.annotator = None
            self.handler = None
            self.config_list = None

    def annotate_emotions(self, text):
        """
        Annotate the emotions in the text.
        :param text: the text to annotate
        :return:
        """
        if self.annotator is None:
            return []

        self.handler.initiate_chat(
            self.annotator,
            silent=True,
            message=f"""Read the following text and annotate it with the emotions it elicits. 
                - Use the GoEmotions taxonomy, which includes: admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise, and trust.
                - Do not write additional text to the identified emotions. 
                \n\n##START TEXT##\n\n{text}\n\n#END TEXT##""",
        )

        res = self.handler.chat_messages[self.annotator][-1]["content"]
        emotions = self.__clean_emotion(res)
        return emotions

    def annotate_topics(self, text):
        """
        Annotate the topics in the text.

        :param text: the text to annotate
        :return:
        """
        if self.annotator is None:
            return []

        self.handler.initiate_chat(
            self.annotator,
            silent=True,
            message=f"""Read the following text and detect 3 general topic discussed in it; 
                    - Each topic must be described 2 words; 
                    - Format your response as follows. 
                    \n\n #T: First Topic; #T: Second Topic; #T: Third Topic.",
                    \n\n##START TEXT##\n\n{text}\n\n#END TEXT##""",
        )

        res = self.handler.chat_messages[self.annotator][-1]["content"]

        topics = re.findall(r"[#T]: \w+ \w+", res)
        topics = [x.split(": ")[1] for x in topics if "Topic" not in x]

        return topics

    def __clean_emotion(self, text):
        """
        Clean the emotion annotation.
        :param text: the text to clean
        :return:
        """
        emotions = {
            "admiration": None,
            "amusement": None,
            "anger": None,
            "annoyance": None,
            "approval": None,
            "caring": None,
            "confusion": None,
            "curiosity": None,
            "desire": None,
            "disappointment": None,
            "disapproval": None,
            "disgust": None,
            "embarrassment": None,
            "excitement": None,
            "fear": None,
            "gratitude": None,
            "grief": None,
            "joy": None,
            "love": None,
            "nervousness": None,
            "optimism": None,
            "pride": None,
            "realization": None,
            "relief": None,
            "remorse": None,
            "sadness": None,
            "surprise": None,
            "trust": None,
        }
        try:
            emotion_eval = [
                e.strip()
                for e in text.replace("'", " ")
                .replace('"', " ")
                .replace("*", "")
                .replace(":", " ")
                .replace("[", " ")
                .replace("]", " ")
                .replace(",", " ")
                .split(" ")
                if e.strip() in emotions
            ]
        except:
            emotion_eval = []
        return emotion_eval

    def extract_components(self, text, c_type="hashtags"):
        """
        Extract the components from the text.

        :param text: the text to extract the components from
        :param c_type: the component type
        :return: the extracted components
        """
        # Define the regex pattern
        if c_type == "hashtags":
            pattern = re.compile(r"#\w+")
        elif c_type == "mentions":
            pattern = re.compile(r"@\w+")
        else:
            return []
        # Find all matches in the input text
        hashtags = pattern.findall(text)
        return hashtags
