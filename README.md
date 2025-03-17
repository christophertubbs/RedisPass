# RedisPass
A simple wrapper library for establishing repeated connections to redis/valkey through a simple store of connection parameters

RedisPass is just a pass through straight to redis-py for the most part - the only things the interface adds is four functions:

- `Credential`
- `get_connection`
- `get_connection_by_host`
- `register`

It's probably easy enough to just copy and paste `redis_pass.__init__.py` into a helpful place rather than actually installing.
## Usage

```python
import redis_pass

# Form a regular connection
connection: redis_pass.Redis = redis_pass.Redis("some-website.used.for.example")
connection.ping()
```
```
Traceback (most recent call last):
  File "<input>", line 1, in <module>
  File "...\site-packages\redis\client.py", line 1378, in ping
    return self.execute_command('PING')
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "...\site-packages\redis\client.py", line 901, in execute_command
    return self.parse_response(conn, command_name, **options)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "...\site-packages\redis\client.py", line 915, in parse_response
    response = connection.read_response()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "...\site-packages\redis\connection.py", line 739, in read_response
    response = self._parser.read_response()
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "...\site-packages\redis\connection.py", line 340, in read_response
    raise error
redis.exceptions.AuthenticationError: Authentication required.
```

```python
import redis_pass
connection: redis_pass.Redis = redis_pass.Redis(
    host="some-website.used.for.example",
    port=8675,
    username="Goober",
    password="Geiber"
)
connection.ping()
# True
connection.set("Here_is_my_test_value", 9)
redis_pass.register(connection=connection)

# Some time later...

connection = redis_pass.get_connection_by_host("some-website.used.for.example")
print(connection.get("Here_is_my_test_value"))
# b'9'
```
