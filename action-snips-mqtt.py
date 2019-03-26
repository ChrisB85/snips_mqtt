#!/usr/bin/env python3
from hermes_python.hermes import Hermes
from hermes_python.ontology import *
import paho.mqtt.client as mqtt
import mqtt_client
import io, time
from pprint import pprint

# Intent slots
USERNAME_PREFIX = mqtt_client.get_config().get('global', 'prefix')

intents = mqtt_client.get_config().get('global', 'intent').split(",")
INTENT_FILTER_START_SESSION = []
for x in intents:
    INTENT_FILTER_START_SESSION.append(USERNAME_PREFIX + x.strip())

# Answers slots
INTENT_INTERRUPT = USERNAME_PREFIX + "Interrupt"
INTENT_DOES_NOT_KNOW = USERNAME_PREFIX + "DoesNotKnow"

answers = mqtt_client.get_config().get('global', 'intent_answer').split(",")
INTENT_FILTER_GET_ANSWER = []
for a in answers:
    INTENT_FILTER_GET_ANSWER.append(USERNAME_PREFIX + a.strip())

SessionsStates = {}


def _set_not_none_dict_value(to_update, update):
    to_update = to_update or {}
    pprint(update)
    for key, value in update.items():
        if value is not None:
            to_update[key] = value
    return to_update


def save_session_state(sessions_states, session_id, new_state):
    sessions_states[session_id] = _set_not_none_dict_value(sessions_states.get(session_id), new_state)


def remove_session_state(sessions_states, session_id):
    sessions_states[session_id] = None


def get_intent_site_id(intent_message):
    return intent_message.site_id


def get_intent_msg(intent_message):
    return intent_message.intent.intent_name.split(':')[-1]


def get_intent_question(x):
    return {
        "IWant": "Co chcesz robić?",
        "TurnOn" : "Co chcesz włączyć?",
        "TurnOff" : "Co chcesz wyłączyć?",
        "Mute" : "Co chcesz wyciszyć?",
        "Unmute" : "Czego dźwięk chcesz przywrócić?",
        "Play" : "Co chcesz odtworzyć?",
        "Pause" : "Co chcesz wstrzymać?",
        "Stop" : "Co chcesz zatrzymać?",
        "clear_room": "Które pomieszczenie?"
#        "command": "Co chcesz zrobić?"
    }.get(x, "")


def get_intent_slots(intent_message):
    slots = []
    if (intent_message.slots is None):
        return slots
    slots_count = len(intent_message.slots.intent_slot)
    for x in range(slots_count):
        slots.append(intent_message.slots.intent_slot[x].slot_value.value.value)
    return slots


def get_locations(intent_message):
    slots = []
    if (intent_message.slots is None):
        return slots
    slots_count = len(intent_message.slots.location)
    for x in range(slots_count):
        slots.append(intent_message.slots.location[x].slot_value.value.value)
    return slots


def start_session(hermes, intent_message):
    session_id = intent_message.session_id
    intent_msg_name = intent_message.intent.intent_name
    pprint(intent_msg_name)
    pprint(INTENT_FILTER_START_SESSION)
    if intent_msg_name not in INTENT_FILTER_START_SESSION:
        return

    print("Starting device control session " + session_id)
    intent_slots = get_intent_slots(intent_message)
    locations = get_locations(intent_message)
    session_state = {"siteId": get_intent_site_id(intent_message), "topic": get_intent_msg(intent_message), "slot": intent_slots, "location": locations}

    # device = intent_message.slots.device.first()
    if len(intent_slots) == 0:
        question = get_intent_question(session_state.get("topic").split(':')[-1])
        pprint(question)
        if question == "":
            hermes.publish_end_session(session_id, "Przepraszam, nie zrozumiałem")
        save_session_state(SessionsStates, session_id, session_state)
        hermes.publish_continue_session(session_id, question, INTENT_FILTER_GET_ANSWER)
    else:
        session_state["slot"] = intent_slots
        session_state["location"] = locations
        site_id = str(session_state.get("siteId"))
        topic = str(session_state.get("topic"))
        payloads = session_state.get("slot")
        pprint(payloads)
        payload_suffix = ""
        if len(locations) >= 1:
            payload_suffix = "/" + str(session_state.get("location")[0])
        for payload in payloads:
            payload = payload + payload_suffix
            mqtt_client.put(site_id + "/" + topic, payload)
            mqtt_client.put(topic + "/" + site_id, payload)
        hermes.publish_end_session(session_id, None)


def user_gives_answer(hermes, intent_message):
    print("User is giving an answer")
    session_id = intent_message.session_id
    print(session_id)
    session_state = SessionsStates.get(session_id)
    session_state, sentence, continues = check_user_answer(session_state, intent_message)

    if session_state is None:
        session_state = {"siteId": get_intent_site_id(intent_message), "topic": get_intent_msg(intent_message), "slot": get_intent_slots(intent_message)}

    if not continues:
        site_id = str(session_state.get("siteId"))
        topic = str(session_state.get("topic"))
        payloads = session_state.get("slot")
        if len(payloads) == 0:
            hermes.publish_end_session(session_id, "Przepraszam, nie zrozumiałem")
        locations = get_locations(intent_message)
        payload_suffix = ""
        if len(locations) >= 1:
            payload_suffix = "/" + str(locations[0])
        for payload in payloads:
            payload = payload + payload_suffix
            mqtt_client.put(site_id + "/" + topic, payload)
            mqtt_client.put(topic + "/" + site_id, payload)
        remove_session_state(SessionsStates, session_id)
        hermes.publish_end_session(session_id, None)
        return

    hermes.publish_continue_session(session_id, sentence, INTENT_FILTER_GET_ANSWER)


def user_quits(hermes, intent_message):
    print("User wants to quit")
    session_id = intent_message.session_id

    remove_session_state(SessionsStates, session_id)
    hermes.publish_end_session(session_id, "OK, nie ma problemu")


def check_user_answer(session_state, intent_message):
    if session_state is None:
        print("session_state is None ==> intent triggered outside of dialog session")
        return session_state, "", False

    answer = get_intent_slots(intent_message)
    # We just try keep listening to the user until we get an answer
    if len(answer) == 0:
        return session_state, "Możesz powtórzyć?", True

    session_state["slot"] = answer
    return session_state, "", False


def session_started(hermes, session_ended_message):
    return


def session_ended(hermes, session_ended_message):
    return


with Hermes(mqtt_options = mqtt_client.get_mqtt_options()) as h:
    h.subscribe_intents(start_session)
    for a in INTENT_FILTER_GET_ANSWER:
        h.subscribe_intent(a, user_gives_answer)
    h.subscribe_intent(INTENT_INTERRUPT, user_quits) \
        .subscribe_session_ended(session_ended) \
        .subscribe_session_started(session_started) \
        .start()
