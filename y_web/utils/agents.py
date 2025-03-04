import random
import faker
import numpy as np
from y_web import db
from y_web.models import Population, Agent, Agent_Population


def __sample_age(mean, std_dev, min_age, max_age):
    """Sample an age from a Gaussian distribution while ensuring it falls within [min_age, max_age]."""
    while True:
        age = np.random.normal(mean, std_dev)  # Sample from Gaussian
        if min_age <= age <= max_age:  # Ensure it's within the range
            return int(round(age))


def __sample_pareto(values, alpha=2.0):
    """Sample a value from the given set following a Pareto distribution."""
    pareto_sample = np.random.pareto(alpha)  # Shifted Pareto sample
    normalized_sample = pareto_sample / (pareto_sample + 1)  # Normalize to (0,1)

    # Map the continuous value to the discrete set
    return values[int(np.floor(normalized_sample * len(values)))]


def generate_population(population_name):
    """
    Generate a fake user
    :param population_name: the name of the population
    """

    # get population by name
    population = Population.query.filter_by(name=population_name).first()

    for _ in range(population.size):
        try:
            nationality = random.sample(population.nationalities.split(","), 1)[
                0
            ].strip()
        except:
            nationality = "American"

        gender = random.sample(["male", "female"], 1)[0]

        fake = faker.Faker(__locales[nationality])

        if gender == "male":
            name = fake.name_male()
        else:
            name = fake.name_female()

        political_leaning = fake.random_element(
            elements=(population.leanings.split(","))
        ).strip()

        # Gaussian distribution for age
        age = __sample_age(
            np.mean([population.age_min, population.age_max]),
            int((population.age_max - population.age_min) / 2),
            population.age_min,
            population.age_max,
        )

        interests = fake.random_elements(
            elements=set(population.interests.split(",")),
            length=fake.random_int(
                min=1,
                max=5,
            ),
        )

        toxicity = fake.random_element(
            elements=(population.toxicity.split(","))
        ).strip()
        language = fake.random_element(
            elements=(population.languages.split(","))
        ).strip()
        ag_type = population.llm

        oe = fake.random_element(elements=("inventive/curious", "consistent/cautious"))
        co = fake.random_element(
            elements=("efficient/organized", "extravagant/careless")
        )
        ex = fake.random_element(elements=("outgoing/energetic", "solitary/reserved"))
        ag = fake.random_element(
            elements=("friendly/compassionate", "critical/judgmental")
        )
        ne = fake.random_element(elements=("sensitive/nervous", "resilient/confident"))

        education_level = fake.random_element(
            elements=(population.education.split(","))
        )

        try:
            round_actions = fake.random_int(
                min=1,
                max=4,
            )
        except:
            round_actions = 3

        daily_activity_level = __sample_pareto([1, 2, 3, 4, 5])

        agent = Agent(
            name=name.replace(" ", ""),
            age=age,
            ag_type=ag_type,
            leaning=political_leaning,
            interests=",".join(list(interests)),
            ag=ag,
            co=co,
            oe=oe,
            ne=ne,
            ex=ex,
            language=language,
            education_level=education_level,
            round_actions=round_actions,
            gender=gender,
            nationality=nationality,
            toxicity=toxicity,
            frecsys=population.frecsys,
            crecsys=population.crecsys,
            daily_activity_level=daily_activity_level,
        )

        db.session.add(agent)
        db.session.commit()

        agent_population = Agent_Population(
            agent_id=agent.id, population_id=population.id
        )

        db.session.add(agent_population)
        db.session.commit()


__locales = {
    "American": "en_US",
    "Argentine": "es_AR",
    "Armenian": "hy_AM",
    "Austrian": "de_AT",
    "Azerbaijani": "az_AZ",
    "Bangladeshi": "bn_BD",
    "Belgian": "nl_BE",
    "Brazilian": "pt_BR",
    "British": "en_GB",
    "Bulgarian": "bg_BG",
    "Chilean": "es_CL",
    "Chinese": "zh_CN",
    "Colombian": "es_CO",
    "Croatian": "hr_HR",
    "Czech": "cs_CZ",
    "Danish": "da_DK",
    "Dutch": "nl_NL",
    "Estonian": "et_EE",
    "Finnish": "fi_FI",
    "French": "fr_FR",
    "Georgian": "ka_GE",
    "German": "de_DE",
    "Greek": "el_GR",
    "Hungarian": "hu_HU",
    "Indian": "en_IN",
    "Indonesian": "id_ID",
    "Iranian": "fa_IR",
    "Irish": "ga_IE",
    "Israeli": "he_IL",
    "Italian": "it_IT",
    "Japanese": "ja_JP",
    "Latvian": "lv_LV",
    "Lithuanian": "lt_LT",
    "Mexican": "es_MX",
    "Nepalese": "ne_NP",
    "New Zealander": "en_NZ",
    "Norwegian": "no_NO",
    "Palestinian": "ar_PS",
    "Polish": "pl_PL",
    "Portuguese": "pt_PT",
    "Romanian": "ro_RO",
    "Russian": "ru_RU",
    "Saudi": "ar_SA",
    "Slovak": "sk_SK",
    "Slovenian": "sl_SI",
    "South African": "zu_ZA",
    "South Korean": "ko_KR",
    "Spanish": "es_ES",
    "Swedish": "sv_SE",
    "Swiss": "de_CH",
    "Taiwanese": "zh_TW",
    "Thai": "th_TH",
    "Turkish": "tr_TR",
    "Ukrainian": "uk_UA",
}
