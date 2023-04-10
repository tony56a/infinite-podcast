import redis
import logging

logger = logging.getLogger()


class RedisClient:
    def __init__(self, config):
        self.redis_client = redis.Redis(
            host=config["redis"]["host"], port=config["redis"]["port"] or 6379
        )
        self.script_queue = config["redis"]["job_queue"]
        self.requested_script_queue = config["redis"]["requested_job_queue"]
        self.script_request_queue = config["redis"]["request_queue"]
        self.script_request_response_queue = config["redis"]["request_response_queue"]

    def get_length(self, queue=None):
        queue = queue or self.script_queue
        return self.redis_client.llen(queue)

    def push(self, payload, queue=None):
        if payload == None:
            return
        queue = queue or self.script_queue

        self.redis_client.lpush(queue, str(payload))

    def priority_push(self, payload, queue=None):
        if payload == None:
            return
        queue = queue or self.script_queue

        self.redis_client.rpush(queue, str(payload))

    def get_queue_content(self, queue=None):
        queue = queue or self.script_queue
        content = self.redis_client.rpop(queue)
        if content:
            return content.decode("utf-8")
        else:
            return None

    def read_next_entries(self, queue=None, entries=3):
        queue = queue or self.script_queue
        content = self.redis_client.lrange(queue, -1 * entries, -1)
        return [entry.decode("utf-8") for entry in content]

    def add(self, key, payload):
        if payload == None:
            return

        self.redis_client.set(key, payload)

    def add(self, key, payload):
        if payload == None:
            return

        self.redis_client.set(key, str(payload))

    def get(self, key):
        return self.redis_client.get(key).decode("utf-8")

    def get_keys(self, search_string):
        return self.redis_client.scan(0, search_string, count=50)
