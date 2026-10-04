"""The HTTP routes, grouped by the partition they serve.

Each module here owns one router and nothing else: the handlers read the service
from ``request.app.state`` and return its models, so status codes live in
``app/errors.py`` and DynamoDB lives in the repository.
"""
