def get_intent_question(x):
    return {
        "IWant": "What do you want to do?",
        "TurnOn" : "What do you want to turn on?",
        "TurnOff" : "What do you want to turn off?",
        "Mute" : "What do you want to mute?",
        "Unmute" : "What do you want to unmute?",
        "Play" : "What do you want to play?",
        "Pause" : "What do you want to pause?",
        "Stop" : "What do you want to stop?"
    }.get(x, "")


def get_intent_slots(intent_message):
    slots_count = len(intent_message.slots.intent_slot)
    slots = []
    for x in range(slots_count):
        slots.append(intent_message.slots.intent_slot[x].slot_value.value.value)
    return slots
