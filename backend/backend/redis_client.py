import redis
import logging

logger = logging.getLogger()


class RedisClient:
    def __init__(self, config):
        self.redis_client = redis.Redis(
            host=config["redis"]["host"], port=config["redis"]["port"] or 6379
        )
        self.redis_list = config["redis"]["job_queue"]

    def get_length(self):
        return self.redis_client.llen(self.redis_list)

    def push(self, payload):
        if payload == None:
            return

        self.redis_client.lpush(self.redis_list, str(payload))

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
