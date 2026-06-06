from __future__ import annotations


MODEL_TIMEOUT_PREFIX = "The local AI model did not answer quickly enough."


def built_in_answer(user_input: str) -> str | None:
    text = user_input.lower()
    if "embedded" in text or "embeded" in text:
        return _embedded_systems_answer()
    return None


def is_model_timeout(answer: str | None) -> bool:
    return bool(answer and answer.startswith(MODEL_TIMEOUT_PREFIX))


def _embedded_systems_answer() -> str:
    return (
        "Embedded systems are small computers built inside a product to control one specific job.\n\n"
        "In a normal computer, you open many apps: browser, games, editor, video player. "
        "In an embedded system, the computer is usually hidden inside the device and keeps doing one focused task. "
        "Examples are a washing machine controller, TV remote, bike ECU, smart meter, router, printer, drone flight controller, "
        "medical device, or a sensor node in an IoT system.\n\n"
        "The main parts are:\n"
        "1. Microcontroller or processor: the brain that runs the program.\n"
        "2. Firmware: the code stored inside the chip, usually written in C, C++, Rust, MicroPython, or assembly.\n"
        "3. Inputs: sensors, buttons, switches, camera, microphone, temperature sensor, voltage reading, etc.\n"
        "4. Outputs: motor, relay, display, LED, speaker, heater, valve, or communication signal.\n"
        "5. Communication: UART, I2C, SPI, CAN, USB, Bluetooth, Wi-Fi, Ethernet, or RF.\n"
        "6. Power system: battery, regulator, charger, protection circuit, and power-saving modes.\n\n"
        "A simple example: in a temperature controller, the sensor reads temperature, the microcontroller compares it with the target, "
        "and then turns a fan or heater on/off. That loop repeats again and again.\n\n"
        "The deep idea is this: embedded systems connect software to the physical world. "
        "Code is not just showing text on a screen; it is reading real voltages, timing signals, controlling current, protecting hardware, "
        "and reacting within strict time limits. That is why embedded work needs both programming knowledge and electronics knowledge.\n\n"
        "Important concepts:\n"
        "- Real-time behavior: some actions must happen within microseconds or milliseconds.\n"
        "- Interrupts: the chip can pause normal code to handle urgent events, like a button press or incoming data.\n"
        "- Memory limits: many chips have tiny RAM/Flash compared with PCs.\n"
        "- Reliability: a bug can stop a motor, damage hardware, or create unsafe behavior.\n"
        "- Debugging: you use multimeters, oscilloscopes, logic analyzers, serial logs, JTAG/SWD, and careful measurement.\n\n"
        "So in one sentence: an embedded system is a dedicated computer inside a device that senses, decides, and controls hardware."
    )
