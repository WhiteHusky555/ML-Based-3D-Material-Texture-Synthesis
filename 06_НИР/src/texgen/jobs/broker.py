"""Долговечные очереди стенда. Сообщение содержит только UUID задания."""
import os
from contextlib import contextmanager
from uuid import UUID

STAGES = ("noise", "generation", "pbr")


@contextmanager
def channel():
    import pika
    params = pika.ConnectionParameters(
        host=os.environ.get("AMQP_HOST", "rabbitmq"),
        credentials=pika.PlainCredentials(os.environ["AMQP_USER"], os.environ["AMQP_PASSWORD"]),
        blocked_connection_timeout=30,
        heartbeat=0,
    )
    conn = pika.BlockingConnection(params)
    try:
        ch = conn.channel()
        for stage in STAGES:
            ch.queue_declare(queue=stage, durable=True, arguments={"x-queue-type": "quorum"})
        ch.confirm_delivery()
        yield ch
    finally:
        if conn.is_open:
            conn.close()


def publish(ch, stage, job):
    import pika
    ch.basic_publish(exchange="", routing_key=stage, body=str(UUID(str(job))).encode(),
                     mandatory=True, properties=pika.BasicProperties(delivery_mode=2))
