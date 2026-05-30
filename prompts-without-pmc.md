# Prompts — WITHOUT PMC (3 FastAPI Fixes)

Copy-paste these one at a time. These are natural developer prompts — no mention of PMC.

## Task 1 — Easy (BackgroundTasks)

```
Hey, I noticed something in the background.py file. The add_task function doesn't check if func is None before calling super().add_task(). Can you add a None check and raise a ValueError with a message like "func parameter cannot be None" if it is? The return type is already fine.
```

## Task 2 — Medium (Routing fix)

```
Yo, there's a weird bug in routing.py. There's a function called request_response that has an inner async def app() that shadows another async def app() in the same scope. Can you fix the naming conflict? The inner one should be renamed. Check around line 110 in fastapi/routing.py.
```

## Task 3 — Hard (Middleware validation)

```
I need a way to validate middleware ordering in the FastAPI app initialization. The idea is that security middleware like CORSMiddleware should come before other middleware in the stack, otherwise it might not work correctly. Can you add a validation method in the FastAPI class that checks this and logs a warning if something's misordered? Take a look at how middleware is set up in applications.py.
```
