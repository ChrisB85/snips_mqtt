#!/usr/bin/env python3
from hermes_python.hermes import Hermes
from hermes_python.ontology import *
import paho.mqtt.client as mqtt
import config as c
import io, time, configparser
from pprint import pprint

CONFIGURATION_ENCODING_FORMAT = "utf-8"
CONFIG_INI = "config.ini"
Config = configparser.ConfigParser()
Config.read(CONFIG_INI)

USERNAME_PREFIX = Config.get('global', 'prefix')

intents = Config.get('global', 'intent').split(",")
INTENT_FILTER_START_SESSION = []
for x in intents:
    INTENT_FILTER_START_SESSION.append(USERNAME_PREFIX + x.strip())

MQTT_IP_ADDR = Config.get('secret', 'host')
MQTT_PORT = Config.get('secret', 'port')
MQTT_USER = Config.get('secret', 'user')
MQTT_PASS = Config.get('secret', 'pass')
MQTT_ADDR = "{}:{}".format(MQTT_IP_ADDR, str(MQTT_PORT))

# Answers slots
INTENT_INTERRUPT = USERNAME_PREFIX + "Interrupt"
INTENT_DOES_NOT_KNOW = USERNAME_PREFIX + "DoesNotKnow"

answers = Config.get('global', 'intent_answer').split(",")
INTENT_FILTER_GET_ANSWER = []
for a in answers:
    INTENT_FILTER_GET_ANSWER.append(USERNAME_PREFIX + a.strip())
pprint(INTENT_FILTER_GET_ANSWER)

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


def put_mqtt(ip, port, topic, payload, username, password):
    client = mqtt.Client("Client")  # create new instance
    client.username_pw_set(username, password)
    client.connect(ip, int(port))  # connect to broker
    if isinstance(payload, str):
        payload = [payload]
    payload_count = len(payload)
    for p in payload:
        print("Publishing " + topic + " / " + p.lower())
        msg = client.publish(topic, p.lower())
        if msg is not None:
            msg.wait_for_publish()
        if payload_count > 1:
            time.sleep(100.0 / 1000.0)
    client.disconnect()


def get_intent_site_id(intent_message):
    return intent_message.site_id


def get_intent_msg(intent_message):
    return intent_message.intent.intent_name.split(':')[-1]


def start_session(hermes, intent_message):
    session_id = intent_message.session_id
    intent_msg_name = intent_message.intent.intent_name
    if intent_msg_name not in INTENT_FILTER_START_SESSION:
        return

    print("Starting device control session " + session_id)
    session_state = {"siteId": get_intent_site_id(intent_message), "topic": get_intent_msg(intent_message), "slot": []}

    # device = intent_message.slots.device.first()
    intent_slots = c.get_intent_slots(intent_message)
    if len(intent_slots) == 0:
        save_session_state(SessionsStates, session_id, session_state)
        hermes.publish_continue_session(session_id,
                                        c.get_intent_question(session_state.get("topic").split(':')[-1]),
                                        INTENT_FILTER_GET_ANSWER)
    else:
        session_state["slot"] = c.get_intent_slots(intent_message)
        put_mqtt(MQTT_IP_ADDR, MQTT_PORT, session_state.get("siteId") + "/" + session_state.get("topic"),
                 session_state.get("slot"), MQTT_USER, MQTT_PASS)
        hermes.publish_end_session(session_id, None)


def user_gives_answer(hermes, intent_message):
    print("User is giving an answer")
    session_id = intent_message.session_id
    print(session_id)
    session_state = SessionsStates.get(session_id)
    session_state, sentence, continues = check_user_answer(session_state, intent_message)

    if session_state is None:
        session_state = {"siteId": get_intent_site_id(intent_message), "topic": get_intent_msg(intent_message), "slot": c.get_intent_slots(intent_message)}

#    print(session_state.get("slot"))
    if not continues:
        put_mqtt(MQTT_IP_ADDR, MQTT_PORT, session_state.get("siteId") + "/" + session_state.get("topic"),
                 session_state.get("slot"), MQTT_USER, MQTT_PASS)
        remove_session_state(SessionsStates, session_id)
        hermes.publish_end_session(session_id, None)
        return

    hermes.publish_continue_session(session_id, sentence, INTENT_FILTER_GET_ANSWER)


def user_quits(hermes, intent_message):
    print("User wants to quit")
    session_id = intent_message.session_id

    remove_session_state(SessionsStates, session_id)
    hermes.publish_end_session(session_id, "OK, no problem")


def check_user_answer(session_state, intent_message):
    if session_state is None:
        print("Error: session_state is None ==> intent triggered outside of dialog session")
        return session_state, "", False

    answer = c.get_intent_slots(intent_message)
    # We just try keep listening to the user until we get an answer
    if len(answer) == 0:
        return session_state, "Możesz powtórzyć?", True

    session_state["slot"] = answer
    return session_state, "", False


def session_started(hermes, session_ended_message):
    return


def session_ended(hermes, session_ended_message):
    return


with Hermes(MQTT_ADDR) as h:
    h.subscribe_intents(start_session)
    for a in INTENT_FILTER_GET_ANSWER:
        h.subscribe_intent(a, user_gives_answer)
    h.subscribe_intent(INTENT_INTERRUPT, user_quits) \
        .subscribe_session_ended(session_ended) \
        .subscribe_session_started(session_started) \
        .start()
