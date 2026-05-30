# Prompts — WITH PMC (3 FastAPI Fixes)

Copy-paste these one at a time. PMC will compress the codebase context automatically through the proxy.

## Task 1 — Easy (BackgroundTasks)

```
Add a None check for the func parameter in BackgroundTasks.add_task. If func is None, raise a ValueError with a clear error message saying "func parameter cannot be None". The return type hint is already there. Check the file fastapi/background.py in the codebase.
```

## Task 2 — Medium (Routing fix)

```
There's a nested async def app() inside another async def app() in the request_response function in routing.py. The inner function shadows the outer one. Rename the inner one to inner_app and make sure the code still works correctly. Check fastapi/routing.py around line 110-134 for the exact code.
```

## Task 3 — Hard (Middleware validation)

```
Add a method called _validate_middleware_order to the FastAPI class in applications.py. This method should check the user_middleware list and warn if CORSMiddleware or other security-related middleware is placed AFTER other middleware in the stack. The warning should use the logger from fastapi.logger. Call this method at the end of __init__. Check fastapi/applications.py and fastapi/middleware/ for the existing middleware setup.
```
