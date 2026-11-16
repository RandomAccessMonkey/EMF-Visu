"""Write the API's OpenAPI schema to stdout (input for frontend type generation)."""

import json

from emf_api.main import create_app

print(json.dumps(create_app().openapi(), indent=2))
