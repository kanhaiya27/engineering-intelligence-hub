# Retrieval label review — 36 dev + validation tasks

**For Avaneesh to verify.** A label says *where in the pinned source the answer lives*. Mode R
(retrieval metrics) scores the system against these spans, so a wrong span means a wrong score.

For each task: read the question and answer, then the labelled spans below it (the real text
at the pinned commit). A label is **correct** if these spans contain the evidence needed to
answer the question, and nothing essential is missing.

**How to answer:** reply with the task numbers that are **wrong or incomplete** (and why, if
you know). Every other task is recorded as verified by you, with the date, in
`benchmark/retrieval_labels.py` (`VERIFIED`). The 24 held-out test tasks are not here (they
are labelled only right before the final run).

## 1. `eih-phase1-code-014` (dev, fastapi/fastapi)

**Question.** Explain how solve_dependencies in fastapi/dependencies/utils.py caches dependency results when use_cache=True.

**Answer.** `solve_dependencies` in `fastapi/dependencies/utils.py` takes a `dependency_cache` dict (L532, created at L547) keyed by each sub-dependant's `cache_key` — the dependency callable plus its sorted security scopes (`fastapi/dependencies/models.py` L58). When `use_cache` is true and the key is already present the cached value is reused (L593-594); otherwise the solved value is stored (L605-606). The cache lives for one request, so a dependency used by several parameters runs once per request.

**Labelled evidence:**

- `fastapi/dependencies/utils.py` lines 524–649 — Looks up and stores solved sub-dependencies in dependency_cache when use_cache is set.

```python
async def solve_dependencies(
    *,
    request: Union[Request, WebSocket],
    dependant: Dependant,
    body: Optional[Union[Dict[str, Any], FormData]] = None,
    background_tasks: Optional[StarletteBackgroundTasks] = None,
    response: Optional[Response] = None,
    dependency_overrides_provider: Optional[Any] = None,
    dependency_cache: Optional[Dict[Tuple[Callable[..., Any], Tuple[str]], Any]] = None,
    async_exit_stack: AsyncExitStack,
) -> Tuple[
    Dict[str, Any],
    List[Any],
    Optional[StarletteBackgroundTasks],
    Response,
    Dict[Tuple[Callable[..., Any], Tuple[str]], Any],
]:
    values: Dict[str, Any] = {}
# … 108 more lines
```

- `fastapi/dependencies/models.py` lines 58–58 — Defines cache_key = (call, sorted security scopes), the cache key.

```python
        self.cache_key = (self.call, tuple(sorted(set(self.security_scopes or []))))
```

*Note:* Task corrected 2026-10-05 (approved by Avaneesh Kumar Verma): the cache is 'dependency_cache' keyed by Dependant.cache_key (was 'values'); evidence now points at solve_dependencies (L524-606).

## 2. `eih-phase1-code-015` (dev, pallets/flask)

**Question.** How does Flask's url_for function in src/flask/helpers.py build endpoint URLs?

**Answer.** Flask's `url_for(endpoint, **values)` resolves the endpoint against the routing URL map (`current_app.url_map.bind_to_environ(...)` or `bind(...)`). It converts positional/keyword arguments into path parameters or appends excess arguments as query string parameters.

**Labelled evidence:**

- `src/flask/helpers.py` lines 176–227 — Public url_for; delegates to current_app.url_for.

```python
def url_for(
    endpoint: str,
    *,
    _anchor: str | None = None,
    _method: str | None = None,
    _scheme: str | None = None,
    _external: bool | None = None,
    **values: t.Any,
) -> str:
    """Generate a URL to the given endpoint with the given values.

    This requires an active request or application context, and calls
    :meth:`current_app.url_for() <flask.Flask.url_for>`. See that method
    for full documentation.

    :param endpoint: The endpoint name associated with the URL to
        generate. If this starts with a ``.``, the current blueprint
        name (if any) will be used.
# … 34 more lines
```

- `src/flask/app.py` lines 966–1090 — Builds the URL with the bound URL adapter; extra values become query args.

```python
    def url_for(
        self,
        /,
        endpoint: str,
        *,
        _anchor: str | None = None,
        _method: str | None = None,
        _scheme: str | None = None,
        _external: bool | None = None,
        **values: t.Any,
    ) -> str:
        """Generate a URL to the given endpoint with the given values.

        This is called by :func:`flask.url_for`, and can be called
        directly as well.

        An *endpoint* is the name of a URL rule, usually added with
        :meth:`@app.route() <route>`, and usually the same name as the
# … 107 more lines
```

## 3. `eih-phase1-code-017` (dev, pallets/flask)

**Question.** Explain how the flash() and get_flashed_messages() mechanism works in Flask.

**Answer.** Flask's `flash(message, category)` appends a tuple of `(category, message)` to `session['_flashes']`. `get_flashed_messages(with_categories=..., category_filter=...)` retrieves and removes `_flashes` from the session cookie, ensuring messages are displayed only once.

**Labelled evidence:**

- `src/flask/helpers.py` lines 299–330 — Appends (category, message) to session['_flashes'].

```python
def flash(message: str, category: str = "message") -> None:
    """Flashes a message to the next request.  In order to remove the
    flashed message from the session and to display it to the user,
    the template has to call :func:`get_flashed_messages`.

    .. versionchanged:: 0.3
       `category` parameter added.

    :param message: the message to be flashed.
    :param category: the category for the message.  The following values
                     are recommended: ``'message'`` for any kind of message,
                     ``'error'`` for errors, ``'info'`` for information
                     messages and ``'warning'`` for warnings.  However any
                     kind of string can be used as category.
    """
    # Original implementation:
    #
    #     session.setdefault('_flashes', []).append((category, message))
# … 14 more lines
```

- `src/flask/helpers.py` lines 333–372 — Pops _flashes from the session, with category filtering.

```python
def get_flashed_messages(
    with_categories: bool = False, category_filter: t.Iterable[str] = ()
) -> list[str] | list[tuple[str, str]]:
    """Pulls all flashed messages from the session and returns them.
    Further calls in the same request to the function will return
    the same messages.  By default just the messages are returned,
    but when `with_categories` is set to ``True``, the return value will
    be a list of tuples in the form ``(category, message)`` instead.

    Filter the flashed messages to one or more categories by providing those
    categories in `category_filter`.  This allows rendering categories in
    separate html blocks.  The `with_categories` and `category_filter`
    arguments are distinct:

    * `with_categories` controls whether categories are returned with message
      text (``True`` gives a tuple, where ``False`` gives just the message text).
    * `category_filter` filters the messages down to only those matching the
      provided categories.
# … 22 more lines
```

## 4. `eih-phase1-code-018` (dev, fastapi/fastapi)

**Question.** How does APIRouter in fastapi/routing.py merge sub-routers via include_router?

**Answer.** In `fastapi/routing.py`, `APIRouter.include_router(router, prefix=..., tags=..., dependencies=...)` iterates through the child router's routes, applies prefixes, merges tags, prepends shared dependencies, and registers the transformed routes into the parent router.

**Labelled evidence:**

- `fastapi/routing.py` lines 1072–1310 — Copies child routes with merged prefix, tags and dependencies.

```python
    def include_router(
        self,
        router: Annotated["APIRouter", Doc("The `APIRouter` to include.")],
        *,
        prefix: Annotated[str, Doc("An optional path prefix for the router.")] = "",
        tags: Annotated[
            Optional[List[Union[str, Enum]]],
            Doc(
                """
                A list of tags to be applied to all the *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).
                """
            ),
# … 221 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence lines 500-600 are APIRoute/APIRouter.__init__; include_router is 1072-1310.

## 5. `eih-phase1-dev-023` (dev, pallets/flask)

**Question.** Write a custom Flask CLI command group `db_cli` with a command `init_db` that uses `with_appcontext`.

**Answer.** ```python
import click
from flask import current_app
from flask.cli import with_appcontext, AppGroup

db_cli = AppGroup('db', help='Database management commands.')

@db_cli.command('init')
@with_appcontext
def init_db_command():
    click.echo(f'Initialized database for {current_app.name}')
```

**Labelled evidence:**

- `src/flask/cli.py` lines 391–423 — Click group whose commands are wrapped in with_appcontext.

```python
class AppGroup(click.Group):
    """This works similar to a regular click :class:`~click.Group` but it
    changes the behavior of the :meth:`command` decorator so that it
    automatically wraps the functions in :func:`with_appcontext`.

    Not to be confused with :class:`FlaskGroup`.
    """

    def command(  # type: ignore[override]
        self, *args: t.Any, **kwargs: t.Any
    ) -> t.Callable[[t.Callable[..., t.Any]], click.Command]:
        """This works exactly like the method of the same name on a regular
        :class:`click.Group` but it wraps callbacks in :func:`with_appcontext`
        unless it's disabled by passing ``with_appcontext=False``.
        """
        wrap_for_ctx = kwargs.pop("with_appcontext", True)

        def decorator(f: t.Callable[..., t.Any]) -> click.Command:
# … 15 more lines
```

- `src/flask/cli.py` lines 366–388 — Decorator that pushes an app context for a command.

```python
def with_appcontext(f: F) -> F:
    """Wraps a callback so that it's guaranteed to be executed with the
    script's application context.

    Custom commands (and their options) registered under ``app.cli`` or
    ``blueprint.cli`` will always have an app context available, this
    decorator is not required in that case.

    .. versionchanged:: 2.2
        The app context is active for subcommands as well as the
        decorated callback. The app context is always available to
        ``app.cli`` command and parameter callbacks.
    """

    @click.pass_context
    def decorator(ctx: click.Context, /, *args: t.Any, **kwargs: t.Any) -> t.Any:
        if not current_app:
            app = ctx.ensure_object(ScriptInfo).load_app()
# … 5 more lines
```

## 6. `eih-phase1-dev-025` (dev, pallets/flask)

**Question.** Write a custom Flask JSON error handler that intercepts 404 Not Found errors and returns a structured JSON payload.

**Answer.** ```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.errorhandler(404)
def handle_not_found(error):
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested URL was not found on this server.',
        'status_code': 404
    }), 404
```

**Labelled evidence:**

- `src/flask/sansio/scaffold.py` lines 597–639 — Decorator registering a handler for a status code or exception.

```python
    @setupmethod
    def errorhandler(
        self, code_or_exception: type[Exception] | int
    ) -> t.Callable[[T_error_handler], T_error_handler]:
        """Register a function to handle errors by code or exception class.

        A decorator that is used to register a function given an
        error code.  Example::

            @app.errorhandler(404)
            def page_not_found(error):
                return 'This page does not exist', 404

        You can also register handlers for arbitrary exceptions::

            @app.errorhandler(DatabaseError)
            def special_exception_handler(error):
                return 'Database connection failed', 500
# … 25 more lines
```

- `src/flask/sansio/scaffold.py` lines 641–654 — Non-decorator form of errorhandler.

```python
    @setupmethod
    def register_error_handler(
        self,
        code_or_exception: type[Exception] | int,
        f: ft.ErrorHandlerCallable,
    ) -> None:
        """Alternative error attach function to the :meth:`errorhandler`
        decorator that is more straightforward to use for non decorator
        usage.

        .. versionadded:: 0.7
        """
        exc_class, code = self._get_exc_class_and_code(code_or_exception)
        self.error_handler_spec[None][code][exc_class] = f
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites src/flask/app.py L1000-1080 (inside Flask.url_for); errorhandler lives in sansio/scaffold.py.

## 7. `eih-phase1-dev-028` (dev, fastapi/fastapi)

**Question.** Write a custom Starlette/FastAPI middleware that measures request execution time and adds an `X-Process-Time` response header.

**Answer.** ```python
import time
from fastapi import FastAPI, Request

app = FastAPI()

@app.middleware('http')
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers['X-Process-Time'] = str(process_time)
    return response
```

**Labelled evidence:**

- `docs/en/docs/tutorial/middleware.md` lines 19–55 — @app.middleware('http'), call_next, and the X-Process-Time example (subsection included).

```
## Create a middleware

To create a middleware you use the decorator `@app.middleware("http")` on top of a function.

The middleware function receives:

* The `request`.
* A function `call_next` that will receive the `request` as a parameter.
    * This function will pass the `request` to the corresponding *path operation*.
    * Then it returns the `response` generated by the corresponding *path operation*.
* You can then modify further the `response` before returning it.

```Python hl_lines="8-9  11  14"
{!../../../docs_src/middleware/tutorial001.py!}
```

!!! tip
    Keep in mind that custom proprietary headers can be added <a href="https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers" class="external-link" target="_blank">using the 'X-' prefix</a>.
# … 19 more lines
```

- `docs_src/middleware/tutorial001.py` lines 1–14 — The add_process_time_header example code included by the doc.

```python
import time

from fastapi import FastAPI, Request

app = FastAPI()


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response
```

## 8. `eih-phase1-dev-030` (dev, fastapi/fastapi)

**Question.** Write a FastAPI lifespan context manager function for database connection startup and teardown.

**Answer.** ```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    print('Connecting to database...')
    yield
    # Teardown logic
    print('Disconnecting from database...')

app = FastAPI(lifespan=lifespan)
```

**Labelled evidence:**

- `docs/en/docs/advanced/events.md` lines 25–90 — The @asynccontextmanager lifespan pattern and FastAPI(lifespan=...).

```
## Lifespan

You can define this *startup* and *shutdown* logic using the `lifespan` parameter of the `FastAPI` app, and a "context manager" (I'll show you what that is in a second).

Let's start with an example and then see it in detail.

We create an async function `lifespan()` with `yield` like this:

```Python hl_lines="16  19"
{!../../../docs_src/events/tutorial003.py!}
```

Here we are simulating the expensive *startup* operation of loading the model by putting the (fake) model function in the dictionary with machine learning models before the `yield`. This code will be executed **before** the application **starts taking requests**, during the *startup*.

And then, right after the `yield`, we unload the model. This code will be executed **after** the application **finishes handling requests**, right before the *shutdown*. This could, for example, release resources like memory or a GPU.

!!! tip
    The `shutdown` would happen when you are **stopping** the application.
# … 48 more lines
```

- `docs_src/events/tutorial003.py` lines 1–28 — The lifespan example code included by the doc.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI


def fake_answer_to_everything_ml_model(x: float):
    return x * 42


ml_models = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the ML model
    ml_models["answer_to_everything"] = fake_answer_to_everything_ml_model
    yield
    # Clean up the ML models and release the resources
# … 10 more lines
```

## 9. `eih-phase1-ops-051` (dev, pallets/flask)

**Question.** Diagnose the root cause of this production traceback: `RuntimeError: Working outside of request context. This typically means that you attempted to use functionality that needed an active HTTP request.`

**Answer.** Root cause: Code attempted to access request-bound proxies like `flask.request` or `flask.session` outside of an active HTTP request cycle (e.g. inside a background worker thread, Celery task, or CLI script). Fix: Pass required data explicitly as function arguments or use `app.test_request_context()` for testing.

**Labelled evidence:**

- `src/flask/globals.py` lines 35–51 — The 'Working outside of request context' message and the request/session proxies that raise it.

```python
_no_req_msg = """\
Working outside of request context.

This typically means that you attempted to use functionality that needed
an active HTTP request. Consult the documentation on testing for
information about how to avoid this problem.\
"""
_cv_request: ContextVar[RequestContext] = ContextVar("flask.request_ctx")
request_ctx: RequestContext = LocalProxy(  # type: ignore[assignment]
    _cv_request, unbound_message=_no_req_msg
)
request: Request = LocalProxy(  # type: ignore[assignment]
    _cv_request, "request", unbound_message=_no_req_msg
)
session: SessionMixin = LocalProxy(  # type: ignore[assignment]
    _cv_request, "session", unbound_message=_no_req_msg
)
```

- `src/flask/app.py` lines 1385–1439 — The fix named in the ground truth for tests.

```python
    def test_request_context(self, *args: t.Any, **kwargs: t.Any) -> RequestContext:
        """Create a :class:`~flask.ctx.RequestContext` for a WSGI
        environment created from the given values. This is mostly useful
        during testing, where you may want to run a function that uses
        request data without dispatching a full request.

        See :doc:`/reqcontext`.

        Use a ``with`` block to push the context, which will make
        :data:`request` point at the request for the created
        environment. ::

            with app.test_request_context(...):
                generate_report()

        When using the shell, it may be easier to push and pop the
        context manually to avoid indentation. ::

# … 37 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites globals.py L30-70 and a function _cv_request_lookup; the file has 51 lines and no such function (the error comes from LocalProxy unbound_message).

## 10. `eih-phase1-ops-054` (dev, fastapi/fastapi)

**Question.** How did FastAPI update its dependency requirements for Pydantic V2 compatibility in version 0.100.0+?

**Answer.** Starting in version 0.100.0, FastAPI added support for Pydantic V2 while retaining backward compatibility with Pydantic V1 using internal adapter utilities in `fastapi._compat`.

**Labelled evidence:**

- `fastapi/_compat.py` lines 28–29 — PYDANTIC_V2 flag selecting the v1/v2 compatibility branch.

```python
PYDANTIC_VERSION = P_VERSION
PYDANTIC_V2 = PYDANTIC_VERSION.startswith("2.")
```

*Note:* Only the version flag is labelled; the v2 and v1 branches (L48 / L282) are large. Release-notes coverage of 0.100.0 not checked; add if found during verification.

## 11. `eih-phase1-ops-058` (dev, fastapi/fastapi)

**Question.** Diagnose this FastAPI error: `RuntimeError: Form data requires python-multipart to be installed`.

**Answer.** Root cause: An endpoint declared `Form(...)` or `File(...)` parameters, but the optional `python-multipart` parsing library is not installed in the environment. Fix: Install `python-multipart` via `pip install python-multipart`.

**Labelled evidence:**

- `fastapi/dependencies/utils.py` lines 67–71 — The exact error text.

```python
multipart_not_installed_error = (
    'Form data requires "python-multipart" to be installed. \n'
    'You can install "python-multipart" with: \n\n'
    "pip install python-multipart\n"
)
```

- `fastapi/dependencies/utils.py` lines 82–100 — Raises RuntimeError(multipart_not_installed_error) when the import fails.

```python
def check_file_field(field: ModelField) -> None:
    field_info = field.field_info
    if isinstance(field_info, params.Form):
        try:
            # __version__ is available in both multiparts, and can be mocked
            from multipart import __version__  # type: ignore

            assert __version__
            try:
                # parse_options_header is only available in the right multipart
                from multipart.multipart import parse_options_header  # type: ignore

                assert parse_options_header
            except ImportError:
                logger.error(multipart_incorrect_install_error)
                raise RuntimeError(multipart_incorrect_install_error) from None
        except ImportError:
            logger.error(multipart_not_installed_error)
# … 1 more lines
```

- `docs/en/docs/tutorial/request-forms.md` lines 5–8 — Docs: install python-multipart to use forms.

```
!!! info
    To use forms, first install <a href="https://github.com/Kludex/python-multipart" class="external-link" target="_blank">`python-multipart`</a>.

    E.g. `pip install python-multipart`.
```

## 12. `eih-phase1-ops-059` (dev, pallets/flask)

**Question.** How did Flask replace `werkzeug.wrappers.Request` with `flask.wrappers.Request`?

**Answer.** `flask.wrappers.Request` subclasses Werkzeug's `Request` to inject Flask-specific conveniences such as `blueprint` name detection, endpoint resolution, JSON parsing helpers (`get_json`), and max content length enforcement.

**Labelled evidence:**

- `src/flask/wrappers.py` lines 18–136 — Flask's Request subclass of Werkzeug's Request.

```python
class Request(RequestBase):
    """The request object used by default in Flask.  Remembers the
    matched endpoint and view arguments.

    It is what ends up as :class:`~flask.request`.  If you want to replace
    the request object used you can subclass this and set
    :attr:`~flask.Flask.request_class` to your subclass.

    The request object is a :class:`~werkzeug.wrappers.Request` subclass and
    provides all of the attributes Werkzeug defines plus a few Flask
    specific ones.
    """

    json_module: t.Any = json

    #: The internal URL rule that matched the request.  This can be
    #: useful to inspect which methods are allowed for the URL from
    #: a before/after handler (``request.url_rule.methods``) etc.
# … 101 more lines
```

## 13. `eih-phase1-req-005` (dev, pallets/flask)

**Question.** What configuration key controls debug mode in Flask 3.x?

**Answer.** In Flask 3.x, debug mode is controlled by app.config['DEBUG'] or the FLASK_DEBUG environment variable when running via the CLI.

**Labelled evidence:**

- `docs/config.rst` lines 68–78 — Documents the DEBUG config key and FLASK_DEBUG.

```
.. py:data:: DEBUG

    Whether debug mode is enabled. When using ``flask run`` to start the development
    server, an interactive debugger will be shown for unhandled exceptions, and the
    server will be reloaded when code changes. The :attr:`~flask.Flask.debug` attribute
    maps to this config key. This is set with the ``FLASK_DEBUG`` environment variable.
    It may not behave as expected if set in code.

    **Do not enable debug mode when deploying in production.**

    Default: ``False``
```

- `docs/config.rst` lines 45–60 — Debug mode via the CLI --debug option / FLASK_DEBUG.

```
Debug Mode
----------

The :data:`DEBUG` config value is special because it may behave inconsistently if
changed after the app has begun setting up. In order to set debug mode reliably, use the
``--debug`` option on the ``flask`` or ``flask run`` command. ``flask run`` will use the
interactive debugger and reloader by default in debug mode.

.. code-block:: text

    $ flask --app hello run --debug

Using the option is recommended. While it is possible to set :data:`DEBUG` in your
config or code, this is strongly discouraged. It can't be read early by the
``flask run`` command, and some systems or extensions may have already configured
themselves based on a previous value.
```

- `src/flask/sansio/app.py` lines 549–567 — app.debug property reads/writes config['DEBUG'].

```python
    @property
    def debug(self) -> bool:
        """Whether debug mode is enabled. When using ``flask run`` to start the
        development server, an interactive debugger will be shown for unhandled
        exceptions, and the server will be reloaded when code changes. This maps to the
        :data:`DEBUG` config key. It may not behave as expected if set late.

        **Do not enable debug mode when deploying in production.**

        Default: ``False``
        """
        return self.config["DEBUG"]  # type: ignore[no-any-return]

    @debug.setter
    def debug(self, value: bool) -> None:
        self.config["DEBUG"] = value

        if self.config["TEMPLATES_AUTO_RELOAD"] is None:
# … 1 more lines
```

- `src/flask/helpers.py` lines 27–32 — Reads FLASK_DEBUG from the environment.

```python
def get_debug_flag() -> bool:
    """Get whether debug mode should be enabled for the app, indicated by the
    :envvar:`FLASK_DEBUG` environment variable. The default is ``False``.
    """
    val = os.environ.get("FLASK_DEBUG")
    return bool(val and val.lower() not in {"0", "false", "no"})
```

## 14. `eih-phase1-req-008` (dev, fastapi/fastapi)

**Question.** What is the requirement for returning background tasks in a FastAPI response?

**Answer.** FastAPI requires declaring a parameter of type `BackgroundTasks` in the route handler function and calling `background_tasks.add_task(task_func, *args, **kwargs)`.

**Labelled evidence:**

- `docs/en/docs/tutorial/background-tasks.md` lines 14–22 — Declare a BackgroundTasks parameter.

```
## Using `BackgroundTasks`

First, import `BackgroundTasks` and define a parameter in your *path operation function* with a type declaration of `BackgroundTasks`:

```Python hl_lines="1  13"
{!../../../docs_src/background_tasks/tutorial001.py!}
```

**FastAPI** will create the object of type `BackgroundTasks` for you and pass it as that parameter.
```

- `docs/en/docs/tutorial/background-tasks.md` lines 40–52 — background_tasks.add_task(...).

```
## Add the background task

Inside of your *path operation function*, pass your task function to the *background tasks* object with the method `.add_task()`:

```Python hl_lines="14"
{!../../../docs_src/background_tasks/tutorial001.py!}
```

`.add_task()` receives as arguments:

* A task function to be run in the background (`write_notification`).
* Any sequence of arguments that should be passed to the task function in order (`email`).
* Any keyword arguments that should be passed to the task function (`message="some notification"`).
```

- `docs_src/background_tasks/tutorial001.py` lines 1–15 — The example code included by the doc.

```python
from fastapi import BackgroundTasks, FastAPI

app = FastAPI()


def write_notification(email: str, message=""):
    with open("log.txt", mode="w") as email_file:
        content = f"notification for {email}: {message}"
        email_file.write(content)


@app.post("/send-notification/{email}")
async def send_notification(email: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(write_notification, email, message="some notification")
    return {"message": "Notification sent in the background"}
```

## 15. `eih-phase1-req-009` (dev, pallets/flask)

**Question.** How does Flask handle signal dispatching with Blinker?

**Answer.** Flask uses the Blinker library for namespace-based signals. Core signals include template_rendered, request_started, request_finished, request_tearing_down, appcontext_pushed, and got_request_exception.

**Labelled evidence:**

- `src/flask/signals.py` lines 1–17 — Blinker Namespace and every core signal.

```python
from __future__ import annotations

from blinker import Namespace

# This namespace is only for signals provided by Flask itself.
_signals = Namespace()

template_rendered = _signals.signal("template-rendered")
before_render_template = _signals.signal("before-render-template")
request_started = _signals.signal("request-started")
request_finished = _signals.signal("request-finished")
request_tearing_down = _signals.signal("request-tearing-down")
got_request_exception = _signals.signal("got-request-exception")
appcontext_tearing_down = _signals.signal("appcontext-tearing-down")
appcontext_pushed = _signals.signal("appcontext-pushed")
appcontext_popped = _signals.signal("appcontext-popped")
message_flashed = _signals.signal("message-flashed")
```

- `docs/signals.rst` lines 20–24 — Docs for the core signals.

```
Core Signals
------------

See :ref:`core-signals-list` for a list of all built-in signals. The :doc:`lifecycle`
page also describes the order that signals and decorators execute.
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites signals.py L10-45; the file has 17 lines.

## 16. `eih-phase1-req-010` (dev, fastapi/fastapi)

**Question.** What OAuth2 password flow security utilities does FastAPI provide in fastapi.security?

**Answer.** FastAPI provides `OAuth2PasswordBearer` and `OAuth2PasswordRequestForm` in `fastapi.security` to extract bearer tokens from the Authorization header and parse standard OAuth2 password request form fields (username, password, scope, grant_type).

**Labelled evidence:**

- `fastapi/security/oauth2.py` lines 391–485 — Extracts the bearer token from the Authorization header.

```python
class OAuth2PasswordBearer(OAuth2):
    """
    OAuth2 flow for authentication using a bearer token obtained with a password.
    An instance of it would be used as a dependency.

    Read more about it in the
    [FastAPI docs for Simple OAuth2 with Password and Bearer](https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/).
    """

    def __init__(
        self,
        tokenUrl: Annotated[
            str,
            Doc(
                """
                The URL to obtain the OAuth2 token. This would be the *path operation*
                that has `OAuth2PasswordRequestForm` as a dependency.
                """
# … 77 more lines
```

- `fastapi/security/oauth2.py` lines 16–149 — Parses username/password/scope/grant_type form fields.

```python
class OAuth2PasswordRequestForm:
    """
    This is a dependency class to collect the `username` and `password` as form data
    for an OAuth2 password flow.

    The OAuth2 specification dictates that for a password flow the data should be
    collected using form data (instead of JSON) and that it should have the specific
    fields `username` and `password`.

    All the initialization parameters are extracted from the request.

    Read more about it in the
    [FastAPI docs for Simple OAuth2 with Password and Bearer](https://fastapi.tiangolo.com/tutorial/security/simple-oauth2/).

    ## Example

    ```python
    from typing import Annotated
# … 116 more lines
```

## 17. `eih-phase1-rev-043` (dev, pallets/flask)

**Question.** Review this Flask snippet: `template = '<h1>Hello ' + request.args.get('name') + '</h1>'; return render_template_string(template)`. Identify the vulnerability.

**Answer.** Defect: Server-Side Template Injection (SSTI, CWE-1336). Dynamically constructing the template string with unescaped user input executes arbitrary Jinja2 template expressions (e.g. `{{ config }}` or RCE payloads). Fix: Pass user input as a template parameter: `render_template_string('<h1>Hello {{ name }}</h1>', name=name)`.

**Labelled evidence:**

- `src/flask/templating.py` lines 153–162 — Renders a template from a source string (the SSTI sink).

```python
def render_template_string(source: str, **context: t.Any) -> str:
    """Render a template from the given source string with the given
    context.

    :param source: The source code of the template to render.
    :param context: The variables to make available in the template.
    """
    app = current_app._get_current_object()  # type: ignore[attr-defined]
    template = app.jinja_env.from_string(source)
    return _render(app, template, context)
```

## 18. `eih-phase1-rev-044` (dev, fastapi/fastapi)

**Question.** Review this FastAPI endpoint: `@app.get('/users/{user_id}') async def get_user(user_id): return {'id': user_id}`. What typing recommendation improves validation and docs?

**Answer.** Recommendation: Add type annotations to `user_id` (e.g. `user_id: int` or `user_id: str = Path(...)`). Without type hints, FastAPI cannot perform automatic type conversion (int coercion), input validation, or generate accurate OpenAPI path parameter schemas.

**Labelled evidence:**

- `docs/en/docs/tutorial/path-params.md` lines 17–28 — Type annotations on path parameters.

```
## Path parameters with types

You can declare the type of a path parameter in the function, using standard Python type annotations:

```Python hl_lines="7"
{!../../../docs_src/path_params/tutorial002.py!}
```

In this case, `item_id` is declared to be an `int`.

!!! check
    This will give you editor support inside of your function, with error checks, completion, etc.
```

- `docs/en/docs/tutorial/path-params.md` lines 43–73 — Validation errors when the annotation does not match.

```
## Data validation

But if you go to the browser at <a href="http://127.0.0.1:8000/items/foo" class="external-link" target="_blank">http://127.0.0.1:8000/items/foo</a>, you will see a nice HTTP error of:

```JSON
{
  "detail": [
    {
      "type": "int_parsing",
      "loc": [
        "path",
        "item_id"
      ],
      "msg": "Input should be a valid integer, unable to parse string as an integer",
      "input": "foo",
      "url": "https://errors.pydantic.dev/2.1/v/int_parsing"
    }
  ]
# … 13 more lines
```

- `fastapi/dependencies/utils.py` lines 207–220 — Reads the endpoint signature's annotations.

```python
def get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
    signature = inspect.signature(call)
    globalns = getattr(call, "__globals__", {})
    typed_params = [
        inspect.Parameter(
            name=param.name,
            kind=param.kind,
            default=param.default,
            annotation=get_typed_annotation(param.annotation, globalns),
        )
        for param in signature.parameters.values()
    ]
    typed_signature = inspect.Signature(typed_params)
    return typed_signature
```

- `fastapi/dependencies/utils.py` lines 317–453 — Turns each annotated parameter into a validated field.

```python
def analyze_param(
    *,
    param_name: str,
    annotation: Any,
    value: Any,
    is_path_param: bool,
) -> Tuple[Any, Optional[params.Depends], Optional[ModelField]]:
    field_info = None
    depends = None
    type_annotation: Any = Any
    use_annotation: Any = Any
    if annotation is not inspect.Signature.empty:
        use_annotation = annotation
        type_annotation = annotation
    if get_origin(use_annotation) is Annotated:
        annotated_args = get_args(annotation)
        type_annotation = annotated_args[0]
        fastapi_annotations = [
# … 119 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites fastapi/routing.py L180-220 (serialize_response..get_request_handler); parameter analysis is in fastapi/dependencies/utils.py.

## 19. `eih-phase1-rev-045` (dev, pallets/flask)

**Question.** Review this Flask route: `@app.route('/items', methods=['POST']) def add(): item = request.json['name']`. What defect occurs if invalid JSON or no payload is sent?

**Answer.** Defect: the route assumes a JSON body with a `name` key. With Flask 3.0 (Werkzeug >= 3.0), `request.json` on a non-JSON or missing body raises 415 Unsupported Media Type; invalid JSON gives 400 Bad Request (`Request.on_json_loading_failed`); a JSON body without `name` raises `KeyError` -> 500. Fix: `data = request.get_json(silent=True) or {}` and validate `data.get('name')`, returning 400 when it is missing.

**Labelled evidence:**

- `src/flask/wrappers.py` lines 129–136 — Turns JSON decode failures into BadRequest.

```python
    def on_json_loading_failed(self, e: ValueError | None) -> t.Any:
        try:
            return super().on_json_loading_failed(e)
        except BadRequest as e:
            if current_app and current_app.debug:
                raise

            raise BadRequest() from e
```

*Note:* Task corrected 2026-10-05 (approved by Avaneesh Kumar Verma): verified by execution on Flask 3.0.3 + Werkzeug 3.1.9 — non-JSON or no body 415, invalid JSON 400, missing key KeyError -> 500.

## 20. `eih-phase1-rev-048` (dev, fastapi/fastapi)

**Question.** Review this FastAPI route: `@app.get('/items') def get_items(limit: int = 10, offset: int = 0): ...`. What happens if a client passes `limit=-5`?

**Answer.** Defect: Missing lower-bound validation. Without constraints, `limit=-5` is accepted as a valid integer, potentially causing negative database slicing errors. Fix: Use `limit: int = Query(default=10, ge=1, le=100)`.

**Labelled evidence:**

- `docs/en/docs/tutorial/path-params-numeric-validations.md` lines 183–208 — ge/le constraints.

```
## Number validations: greater than or equal

With `Query` and `Path` (and others you'll see later) you can declare number constraints.

Here, with `ge=1`, `item_id` will need to be an integer number "`g`reater than or `e`qual" to `1`.

=== "Python 3.9+"

    ```Python hl_lines="10"
    {!> ../../../docs_src/path_params_numeric_validations/tutorial004_an_py39.py!}
    ```

=== "Python 3.8+"

    ```Python hl_lines="9"
    {!> ../../../docs_src/path_params_numeric_validations/tutorial004_an.py!}
    ```

# … 8 more lines
```

- `fastapi/param_functions.py` lines 339–640 — Query(...) accepts ge, gt, le, lt.

```python
def Query(  # noqa: N802
    default: Annotated[
        Any,
        Doc(
            """
            Default value if the parameter field is not set.
            """
        ),
    ] = Undefined,
    *,
    default_factory: Annotated[
        Union[Callable[[], Any], None],
        Doc(
            """
            A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.
# … 284 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites fastapi/params.py L20-50 (Param.__init__ start), not the Query ge/le docs.

## 21. `eih-phase1-test-034` (dev, fastapi/fastapi)

**Question.** Write a pytest test overriding a FastAPI dependency using `app.dependency_overrides`.

**Answer.** ```python
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

app = FastAPI()

def get_db():
    return 'real_db'

@app.get('/data')
def read_data(db=Depends(get_db)):
    return {'db': db}

client = TestClient(app)

def test_override_dependency():
    def mock_get_db():
        return 'mock_db'
    
    app.dependency_overrides[get_db] = mock_get_db
    try:
        response = client.get('/data')
        assert response.json() == {'db': 'mock_db'}
    finally:
        app.dependency_overrides.clear()
```

**Labelled evidence:**

- `docs/en/docs/advanced/testing-dependencies.md` lines 23–81 — How to override and reset.

```
### Use the `app.dependency_overrides` attribute

For these cases, your **FastAPI** application has an attribute `app.dependency_overrides`, it is a simple `dict`.

To override a dependency for testing, you put as a key the original dependency (a function), and as the value, your dependency override (another function).

And then **FastAPI** will call that override instead of the original dependency.

=== "Python 3.10+"

    ```Python hl_lines="26-27  30"
    {!> ../../../docs_src/dependency_testing/tutorial001_an_py310.py!}
    ```

=== "Python 3.9+"

    ```Python hl_lines="28-29  32"
    {!> ../../../docs_src/dependency_testing/tutorial001_an_py39.py!}
# … 41 more lines
```

- `docs_src/dependency_testing/tutorial001.py` lines 1–59 — Example override test code.

```python
from typing import Union

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

app = FastAPI()


async def common_parameters(
    q: Union[str, None] = None, skip: int = 0, limit: int = 100
):
    return {"q": q, "skip": skip, "limit": limit}


@app.get("/items/")
async def read_items(commons: dict = Depends(common_parameters)):
    return {"message": "Hello Items!", "params": commons}

# … 41 more lines
```

## 22. `eih-phase1-test-035` (dev, pallets/flask)

**Question.** Why does accessing `flask.current_app` outside of a request or app context raise `RuntimeError: Working outside of application context` in test suites?

**Answer.** `current_app` is a LocalProxy bound to `_cv_app.get()`. If no `AppContext` has been pushed onto the stack (via `with app.app_context():`), the proxy finds no active application and raises a `RuntimeError`.

**Labelled evidence:**

- `src/flask/globals.py` lines 17–33 — 'Working outside of application context' message and the current_app/g proxies.

```python
_no_app_msg = """\
Working outside of application context.

This typically means that you attempted to use functionality that needed
the current application. To solve this, set up an application context
with app.app_context(). See the documentation for more information.\
"""
_cv_app: ContextVar[AppContext] = ContextVar("flask.app_ctx")
app_ctx: AppContext = LocalProxy(  # type: ignore[assignment]
    _cv_app, unbound_message=_no_app_msg
)
current_app: Flask = LocalProxy(  # type: ignore[assignment]
    _cv_app, "app", unbound_message=_no_app_msg
)
g: _AppCtxGlobals = LocalProxy(  # type: ignore[assignment]
    _cv_app, "g", unbound_message=_no_app_msg
)
```

- `src/flask/ctx.py` lines 251–254 — Pushing an app context binds _cv_app.

```python
    def push(self) -> None:
        """Binds the app context to the current context."""
        self._cv_tokens.append(_cv_app.set(self))
        appcontext_pushed.send(self.app, _async_wrapper=self.app.ensure_sync)
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites globals.py L20-60; the file has 51 lines.

## 23. `eih-phase1-test-037` (dev, pallets/flask)

**Question.** Write a test checking that a Flask session variable persists across multiple requests when using `test_client()`.

**Answer.** ```python
from flask import Flask, session

app = Flask(__name__)
app.secret_key = 'test-secret'

@app.route('/set')
def set_val():
    session['user'] = 'alice'
    return 'ok'

@app.route('/get')
def get_val():
    return session.get('user', 'none')

def test_session_persistence():
    client = app.test_client()
    client.get('/set')
    res = client.get('/get')
    assert res.data.decode('utf-8') == 'alice'
```

**Labelled evidence:**

- `docs/testing.rst` lines 202–240 — Session access with the test client.

```
Accessing and Modifying the Session
-----------------------------------

To access Flask's context variables, mainly
:data:`~flask.session`, use the client in a ``with`` statement.
The app and request context will remain active *after* making a request,
until the ``with`` block ends.

.. code-block:: python

    from flask import session

    def test_access_session(client):
        with client:
            client.post("/auth/login", data={"username": "flask"})
            # session is still accessible
            assert session["user_id"] == 1

# … 21 more lines
```

- `src/flask/testing.py` lines 135–183 — Opens/saves the session around a block.

```python
    @contextmanager
    def session_transaction(
        self, *args: t.Any, **kwargs: t.Any
    ) -> t.Iterator[SessionMixin]:
        """When used in combination with a ``with`` statement this opens a
        session transaction.  This can be used to modify the session that
        the test client uses.  Once the ``with`` block is left the session is
        stored back.

        ::

            with client.session_transaction() as session:
                session['value'] = 42

        Internally this is implemented by going through a temporary test
        request context and since session handling could depend on
        request variables this function accepts the same arguments as
        :meth:`~flask.Flask.test_request_context` which are directly
# … 31 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites testing.py L50-100 (EnvironBuilder), not FlaskClient.

## 24. `eih-phase1-test-038` (dev, fastapi/fastapi)

**Question.** Write an asynchronous pytest test for a FastAPI async endpoint using `httpx.AsyncClient` and `ASGITransport`.

**Answer.** ```python
import pytest
import httpx
from fastapi import FastAPI

app = FastAPI()

@app.get('/async-hello')
async def async_hello():
    return {'message': 'async world'}

@pytest.mark.asyncio
async def test_async_endpoint():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get('/async-hello')
        assert response.status_code == 200
        assert response.json() == {'message': 'async world'}
```

**Labelled evidence:**

- `docs/en/docs/advanced/async-tests.md` lines 21–43 — AsyncClient + ASGITransport example.

```
## Example

For a simple example, let's consider a file structure similar to the one described in [Bigger Applications](../tutorial/bigger-applications.md){.internal-link target=_blank} and [Testing](../tutorial/testing.md){.internal-link target=_blank}:

```
.
├── app
│   ├── __init__.py
│   ├── main.py
│   └── test_main.py
```

The file `main.py` would have:

```Python
{!../../../docs_src/async_tests/main.py!}
```

# … 5 more lines
```

- `docs_src/async_tests/test_main.py` lines 1–12 — The async test included by the doc.

```python
import pytest
from httpx import AsyncClient

from .main import app


@pytest.mark.anyio
async def test_root():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Tomato"}
```

- `docs_src/async_tests/main.py` lines 1–8 — The app under test.

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Tomato"}
```

## 25. `eih-phase1-code-011` (val, pallets/flask)

**Question.** Explain how the RequestContext.push() and pop() methods work in Flask's ctx.py.

**Answer.** In `src/flask/ctx.py`, `RequestContext.push()` pushes the request context onto the context stack (or sets it in ContextVar in modern Python), ensuring an AppContext is also active. It binds request globals (`request`, `session`). `pop()` executes teardown functions registered via `teardown_request` and resets context variables.

**Labelled evidence:**

- `src/flask/ctx.py` lines 367–394 — Pushes app context if needed, sets _cv_request, opens session.

```python
    def push(self) -> None:
        # Before we push the request context we have to ensure that there
        # is an application context.
        app_ctx = _cv_app.get(None)

        if app_ctx is None or app_ctx.app is not self.app:
            app_ctx = self.app.app_context()
            app_ctx.push()
        else:
            app_ctx = None

        self._cv_tokens.append((_cv_request.set(self), app_ctx))

        # Open the session at the moment that the request context is available.
        # This allows a custom open_session method to use the request context.
        # Only open a new session if this is the first time the request was
        # pushed, otherwise stream_with_context loses the session.
        if self.session is None:
# … 10 more lines
```

- `src/flask/ctx.py` lines 396–431 — Runs teardown_request functions and resets the context var.

```python
    def pop(self, exc: BaseException | None = _sentinel) -> None:  # type: ignore
        """Pops the request context and unbinds it by doing that.  This will
        also trigger the execution of functions registered by the
        :meth:`~flask.Flask.teardown_request` decorator.

        .. versionchanged:: 0.9
           Added the `exc` argument.
        """
        clear_request = len(self._cv_tokens) == 1

        try:
            if clear_request:
                if exc is _sentinel:
                    exc = sys.exc_info()[1]
                self.app.do_teardown_request(exc)

                request_close = getattr(self.request, "close", None)
                if request_close is not None:
# … 18 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites ctx.py L200-280 (has_request_context..AppContext); RequestContext.push/pop are 367-431.

## 26. `eih-phase1-code-016` (val, fastapi/fastapi)

**Question.** How does FastAPI handle HTTPException vs Starlette HTTPException in fastapi/exceptions.py?

**Answer.** FastAPI subclassed `starlette.exceptions.HTTPException` to allow passing extra headers and arbitrary JSON-serializable `detail` objects, registering a default exception handler `http_exception_handler` that converts it into a JSONResponse with status code and detail payload.

**Labelled evidence:**

- `fastapi/exceptions.py` lines 9–65 — Subclass of Starlette HTTPException with headers and any detail.

```python
class HTTPException(StarletteHTTPException):
    """
    An HTTP exception you can raise in your own code to show errors to the client.

    This is for client errors, invalid authentication, invalid data, etc. Not for server
    errors in your code.

    Read more about it in the
    [FastAPI docs for Handling Errors](https://fastapi.tiangolo.com/tutorial/handling-errors/).

    ## Example

    ```python
    from fastapi import FastAPI, HTTPException

    app = FastAPI()

    items = {"foo": "The Foo Wrestlers"}
# … 39 more lines
```

- `fastapi/exception_handlers.py` lines 11–17 — Default handler returning a JSONResponse.

```python
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    headers = getattr(exc, "headers", None)
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=headers)
    return JSONResponse(
        {"detail": exc.detail}, status_code=exc.status_code, headers=headers
    )
```

- `docs/en/docs/tutorial/handling-errors.md` lines 22–71 — Docs for raising HTTPException.

```
## Use `HTTPException`

To return HTTP responses with errors to the client you use `HTTPException`.

### Import `HTTPException`

```Python hl_lines="1"
{!../../../docs_src/handling_errors/tutorial001.py!}
```

### Raise an `HTTPException` in your code

`HTTPException` is a normal Python exception with additional data relevant for APIs.

Because it's a Python exception, you don't `return` it, you `raise` it.

This also means that if you are inside a utility function that you are calling inside of your *path operation function*, and you raise the `HTTPException` from inside of that utility function, it won't run the rest of the code in the *path operation function*, it will terminate that request right away and send the HTTP error from the `HTTPException` to the client.

# … 32 more lines
```

## 27. `eih-phase1-dev-021` (val, pallets/flask)

**Question.** Write a minimal Flask application factory function `create_app` that initializes a Flask app, sets config, and registers a health check route returning JSON.

**Answer.** ```python
from flask import Flask, jsonify

def create_app(test_config=None) -> Flask:
    app = Flask(__name__)
    if test_config:
        app.config.update(test_config)

    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy'})

    return app
```

**Labelled evidence:**

- `docs/tutorial/factory.rst` lines 23–122 — create_app(test_config=None) factory.

```
The Application Factory
-----------------------

It's time to start coding! Create the ``flaskr`` directory and add the
``__init__.py`` file. The ``__init__.py`` serves double duty: it will
contain the application factory, and it tells Python that the ``flaskr``
directory should be treated as a package.

.. code-block:: none

    $ mkdir flaskr

.. code-block:: python
    :caption: ``flaskr/__init__.py``

    import os

    from flask import Flask
# … 82 more lines
```

## 28. `eih-phase1-dev-026` (val, fastapi/fastapi)

**Question.** Write a FastAPI endpoint demonstrating `Query` validation with `min_length`, `max_length`, and `regex`.

**Answer.** ```python
from fastapi import FastAPI, Query

app = FastAPI()

@app.get('/search/')
async def search(
    q: str = Query(
        ...,
        min_length=3,
        max_length=50,
        pattern=r'^[a-zA-Z0-9_-]+$',
        description='Search query term'
    )
):
    return {'q': q}
```

**Labelled evidence:**

- `docs/en/docs/tutorial/query-params-str-validations.md` lines 238–276 — min_length / max_length.

```
## Add more validations

You can also add a parameter `min_length`:

=== "Python 3.10+"

    ```Python hl_lines="10"
    {!> ../../../docs_src/query_params_str_validations/tutorial003_an_py310.py!}
    ```

=== "Python 3.9+"

    ```Python hl_lines="10"
    {!> ../../../docs_src/query_params_str_validations/tutorial003_an_py39.py!}
    ```

=== "Python 3.8+"

# … 21 more lines
```

- `docs/en/docs/tutorial/query-params-str-validations.md` lines 278–340 — pattern= (and the old regex=).

```
## Add regular expressions

You can define a <abbr title="A regular expression, regex or regexp is a sequence of characters that define a search pattern for strings.">regular expression</abbr> `pattern` that the parameter should match:

=== "Python 3.10+"

    ```Python hl_lines="11"
    {!> ../../../docs_src/query_params_str_validations/tutorial004_an_py310.py!}
    ```

=== "Python 3.9+"

    ```Python hl_lines="11"
    {!> ../../../docs_src/query_params_str_validations/tutorial004_an_py39.py!}
    ```

=== "Python 3.8+"

# … 45 more lines
```

- `docs_src/query_params_str_validations/tutorial004.py` lines 1–17 — Example with min_length, max_length and pattern.

```python
from typing import Union

from fastapi import FastAPI, Query

app = FastAPI()


@app.get("/items/")
async def read_items(
    q: Union[str, None] = Query(
        default=None, min_length=3, max_length=50, pattern="^fixedquery$"
    ),
):
    results = {"items": [{"item_id": "Foo"}, {"item_id": "Bar"}]}
    if q:
        results.update({"q": q})
    return results
```

- `fastapi/param_functions.py` lines 339–640 — Query(...) signature with the validation arguments.

```python
def Query(  # noqa: N802
    default: Annotated[
        Any,
        Doc(
            """
            Default value if the parameter field is not set.
            """
        ),
    ] = Undefined,
    *,
    default_factory: Annotated[
        Union[Callable[[], Any], None],
        Doc(
            """
            A callable to generate the default value.

            This doesn't affect `Path` parameters as the value is always required.
            The parameter is available only for compatibility.
# … 284 more lines
```

## 29. `eih-phase1-ops-052` (val, fastapi/fastapi)

**Question.** Diagnose this FastAPI startup error: `AssertionError: Cannot specify `Depends` in `Annotated` and default value together for 'db'`.

**Answer.** It is raised by `analyze_param` in `fastapi/dependencies/utils.py` (assertion at L368-371) when one parameter declares its dependency twice: inside `Annotated[..., Depends(x)]` and as a default value `= Depends(y)`. Fix: declare the dependency once, either in `Annotated` or as the default value.

**Labelled evidence:**

- `fastapi/dependencies/utils.py` lines 368–371 — The assertion that raises 'Cannot specify `Depends` in `Annotated` and default value together'.

```python
        assert depends is None, (
            "Cannot specify `Depends` in `Annotated` and default value"
            f" together for {param_name!r}"
        )
```

- `fastapi/dependencies/utils.py` lines 317–453 — Where a parameter's Annotated metadata and default value are analysed.

```python
def analyze_param(
    *,
    param_name: str,
    annotation: Any,
    value: Any,
    is_path_param: bool,
) -> Tuple[Any, Optional[params.Depends], Optional[ModelField]]:
    field_info = None
    depends = None
    type_annotation: Any = Any
    use_annotation: Any = Any
    if annotation is not inspect.Signature.empty:
        use_annotation = annotation
        type_annotation = annotation
    if get_origin(use_annotation) is Annotated:
        annotated_args = get_args(annotation)
        type_annotation = annotated_args[0]
        fastapi_annotations = [
# … 119 more lines
```

*Note:* Task replaced 2026-10-05 (approved by Avaneesh Kumar Verma): the original error 'A dependency cycle was detected in Depends(...)' does not exist in FastAPI at the pinned commit.

## 30. `eih-phase1-ops-053` (val, pallets/flask)

**Question.** Which Flask version removed `json.JSONEncoder` / `JSONDecoder` and the app's `json_encoder` / `json_decoder` attributes, and what replaced them?

**Answer.** They were deprecated in Flask 2.2.0 and removed in Flask 2.3.0. JSON behaviour is now customised through the `app.json` provider interface (`DefaultJSONProvider`) instead of custom encoder/decoder classes.

**Labelled evidence:**

- `CHANGES.rst` lines 78–129 — Removal of json_encoder/json_decoder and json.JSONEncoder/JSONDecoder.

```
Version 2.3.0
-------------

Released 2023-04-25

-   Drop support for Python 3.7. :pr:`5072`
-   Update minimum requirements to the latest versions: Werkzeug>=2.3.0, Jinja2>3.1.2,
    itsdangerous>=2.1.2, click>=8.1.3.
-   Remove previously deprecated code. :pr:`4995`

    -   The ``push`` and ``pop`` methods of the deprecated ``_app_ctx_stack`` and
        ``_request_ctx_stack`` objects are removed. ``top`` still exists to give
        extensions more time to update, but it will be removed.
    -   The ``FLASK_ENV`` environment variable, ``ENV`` config key, and ``app.env``
        property are removed.
    -   The ``session_cookie_name``, ``send_file_max_age_default``, ``use_x_sendfile``,
        ``propagate_exceptions``, and ``templates_auto_reload`` properties on ``app``
        are removed.
# … 34 more lines
```

- `CHANGES.rst` lines 232–235 — 2.2.0 deprecation in favour of the app.json provider interface.

```
-   Setting custom ``json_encoder`` and ``json_decoder`` classes on the
    app or a blueprint, and the corresponding ``json.JSONEncoder`` and
    ``JSONDecoder`` classes, are deprecated. JSON behavior can now be
    overridden using the ``app.json`` provider interface. :pr:`4692`
```

*Note:* Task corrected 2026-10-05 (approved by Avaneesh Kumar Verma): removal is in 2.3.0, not 3.0; tojson_filter dropped from the question.

## 31. `eih-phase1-req-002` (val, fastapi/fastapi)

**Question.** What are FastAPI's requirements for automatic OpenAPI documentation generation?

**Answer.** FastAPI requires standard Python type hints, Pydantic models for request/response payloads, and route decorators (@app.get, @app.post) to automatically build OpenAPI schemas and interactive Swagger UI/ReDoc endpoints at /docs and /redoc.

**Labelled evidence:**

- `docs/en/docs/features.md` lines 12–17 — OpenAPI + JSON Schema.

```
### Based on open standards

* <a href="https://github.com/OAI/OpenAPI-Specification" class="external-link" target="_blank"><strong>OpenAPI</strong></a> for API creation, including declarations of <abbr title="also known as: endpoints, routes">path</abbr> <abbr title="also known as HTTP methods, as POST, GET, PUT, DELETE">operations</abbr>, parameters, body requests, security, etc.
* Automatic data model documentation with <a href="https://json-schema.org/" class="external-link" target="_blank"><strong>JSON Schema</strong></a> (as OpenAPI itself is based on JSON Schema).
* Designed around these standards, after a meticulous study. Instead of an afterthought layer on top.
* This also allows using automatic **client code generation** in many languages.
```

- `docs/en/docs/features.md` lines 19–29 — Swagger UI at /docs and ReDoc at /redoc.

```
### Automatic docs

Interactive API documentation and exploration web user interfaces. As the framework is based on OpenAPI, there are multiple options, 2 included by default.

* <a href="https://github.com/swagger-api/swagger-ui" class="external-link" target="_blank"><strong>Swagger UI</strong></a>, with interactive exploration, call and test your API directly from the browser.

![Swagger UI interaction](https://fastapi.tiangolo.com/img/index/index-03-swagger-02.png)

* Alternative API documentation with <a href="https://github.com/Rebilly/ReDoc" class="external-link" target="_blank"><strong>ReDoc</strong></a>.

![ReDoc](https://fastapi.tiangolo.com/img/index/index-06-redoc-02.png)
```

## 32. `eih-phase1-req-003` (val, pallets/flask)

**Question.** How does Flask structure Blueprint registration and what are the architectural requirements for url_prefix?

**Answer.** Blueprints in Flask represent modular slices of an application. When registering a blueprint via app.register_blueprint(bp, url_prefix=...), the url_prefix prepends to all endpoints defined in the blueprint. Blueprints can also declare their own default url_prefix during initialization.

**Labelled evidence:**

- `docs/blueprints.rst` lines 84–121 — register_blueprint(bp, url_prefix=...).

```
Registering Blueprints
----------------------

So how do you register that blueprint?  Like this::

    from flask import Flask
    from yourapplication.simple_page import simple_page

    app = Flask(__name__)
    app.register_blueprint(simple_page)

If you check the rules registered on the application, you will find
these::

    >>> app.url_map
    Map([<Rule '/static/<filename>' (HEAD, OPTIONS, GET) -> static>,
     <Rule '/<page>' (HEAD, OPTIONS, GET) -> simple_page.show>,
     <Rule '/' (HEAD, OPTIONS, GET) -> simple_page.show>])
# … 20 more lines
```

- `src/flask/sansio/blueprints.py` lines 41–85 — Resolves url_prefix from options or the blueprint default.

```python
    def __init__(
        self,
        blueprint: Blueprint,
        app: App,
        options: t.Any,
        first_registration: bool,
    ) -> None:
        #: a reference to the current application
        self.app = app

        #: a reference to the blueprint that created this setup state.
        self.blueprint = blueprint

        #: a dictionary with all options that were passed to the
        #: :meth:`~flask.Flask.register_blueprint` method.
        self.options = options

        #: as blueprints can be registered multiple times with the
# … 27 more lines
```

- `src/flask/sansio/blueprints.py` lines 273–377 — Registers deferred functions and nested blueprints on the app.

```python
    def register(self, app: App, options: dict[str, t.Any]) -> None:
        """Called by :meth:`Flask.register_blueprint` to register all
        views and callbacks registered on the blueprint with the
        application. Creates a :class:`.BlueprintSetupState` and calls
        each :meth:`record` callback with it.

        :param app: The application this blueprint is being registered
            with.
        :param options: Keyword arguments forwarded from
            :meth:`~Flask.register_blueprint`.

        .. versionchanged:: 2.3
            Nested blueprints now correctly apply subdomains.

        .. versionchanged:: 2.1
            Registering the same blueprint with the same name multiple
            times is an error.

# … 87 more lines
```

- `src/flask/sansio/app.py` lines 569–595 — Entry point called by the app.

```python
    @setupmethod
    def register_blueprint(self, blueprint: Blueprint, **options: t.Any) -> None:
        """Register a :class:`~flask.Blueprint` on the application. Keyword
        arguments passed to this method will override the defaults set on the
        blueprint.

        Calls the blueprint's :meth:`~flask.Blueprint.register` method after
        recording the blueprint in the application's :attr:`blueprints`.

        :param blueprint: The blueprint to register.
        :param url_prefix: Blueprint routes will be prefixed with this.
        :param subdomain: Blueprint routes will match on this subdomain.
        :param url_defaults: Blueprint routes will use these default values for
            view arguments.
        :param options: Additional keyword arguments are passed to
            :class:`~flask.blueprints.BlueprintSetupState`. They can be
            accessed in :meth:`~flask.Blueprint.record` callbacks.

# … 9 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites src/flask/blueprints.py L50-120; Blueprint.register is in sansio/blueprints.py.

## 33. `eih-phase1-rev-046` (val, fastapi/fastapi)

**Question.** Review this FastAPI endpoint: `@app.get('/heavy') async def heavy_calc(): time.sleep(10); return {'status': 'done'}`. What performance defect exists?

**Answer.** Defect: Event loop blocking. Calling blocking synchronous functions (`time.sleep(10)` or synchronous I/O) inside an `async def` route blocks the entire asyncio event loop thread, preventing all other concurrent requests from progressing. Fix: Use `await asyncio.sleep(10)` or define the endpoint as a synchronous `def heavy_calc()` so FastAPI offloads it to a threadpool worker.

**Labelled evidence:**

- `docs/en/docs/async.md` lines 5–52 — Use def, not async def, for blocking libraries.

```
## In a hurry?

<abbr title="too long; didn't read"><strong>TL;DR:</strong></abbr>

If you are using third party libraries that tell you to call them with `await`, like:

```Python
results = await some_library()
```

Then, declare your *path operation functions* with `async def` like:

```Python hl_lines="2"
@app.get('/')
async def read_results():
    results = await some_library()
    return results
```
# … 30 more lines
```

## 34. `eih-phase1-rev-047` (val, pallets/flask)

**Question.** What security risk occurs if Flask's `SECRET_KEY` is hardcoded as `'dev'` in production deployments?

**Answer.** Risk: Session forgery and cryptographic tampering. Anyone knowing the `SECRET_KEY` can forge signed session cookies, hijack user sessions, bypass authentication, and tamper with session data.

**Labelled evidence:**

- `docs/config.rst` lines 114–126 — Secret key used to sign the session cookie.

```
.. py:data:: SECRET_KEY

    A secret key that will be used for securely signing the session cookie
    and can be used for any other security related needs by extensions or your
    application. It should be a long random ``bytes`` or ``str``. For
    example, copy the output of this to your config::

        $ python -c 'import secrets; print(secrets.token_hex())'
        '192b9bdd22ab9ed4d12e236c78afcb9a393ec15f71bbf5dc987d54727823bcbf'

    **Do not reveal the secret key when posting questions or committing code.**

    Default: ``None``
```

- `src/flask/sessions.py` lines 307–318 — Builds the itsdangerous serializer from secret_key.

```python
    def get_signing_serializer(self, app: Flask) -> URLSafeTimedSerializer | None:
        if not app.secret_key:
            return None
        signer_kwargs = dict(
            key_derivation=self.key_derivation, digest_method=self.digest_method
        )
        return URLSafeTimedSerializer(
            app.secret_key,
            salt=self.salt,
            serializer=self.serializer,
            signer_kwargs=signer_kwargs,
        )
```

## 35. `eih-phase1-test-032` (val, fastapi/fastapi)

**Question.** Write a pytest unit test for a FastAPI application using Starlette's `TestClient` verifying POST `/items/`.

**Answer.** ```python
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

app = FastAPI()
class Item(BaseModel):
    name: str

@app.post('/items/')
def create_item(item: Item):
    return item

client = TestClient(app)

def test_create_item():
    response = client.post('/items/', json={'name': 'Widget'})
    assert response.status_code == 200
    assert response.json() == {'name': 'Widget'}
```

**Labelled evidence:**

- `fastapi/testclient.py` lines 1–1 — Re-exports Starlette's TestClient.

```python
from starlette.testclient import TestClient as TestClient  # noqa
```

- `docs/en/docs/tutorial/testing.md` lines 9–43 — TestClient usage.

```
## Using `TestClient`

!!! info
    To use `TestClient`, first install <a href="https://www.python-httpx.org" class="external-link" target="_blank">`httpx`</a>.

    E.g. `pip install httpx`.

Import `TestClient`.

Create a `TestClient` by passing your **FastAPI** application to it.

Create functions with a name that starts with `test_` (this is standard `pytest` conventions).

Use the `TestClient` object the same way as you do with `httpx`.

Write simple `assert` statements with the standard Python expressions that you need to check (again, standard `pytest`).

```Python hl_lines="2  12  15-18"
# … 17 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites testclient.py L1-30; the file has 1 line.

## 36. `eih-phase1-test-033` (val, pallets/flask)

**Question.** Explain how `app.test_cli_runner()` in Flask allows testing Click CLI commands.

**Answer.** In `src/flask/testing.py`, `FlaskCliRunner` extends Click's `CliRunner` by automatically setting up the application context before executing CLI command callbacks, enabling assertions on stdout, stderr, and exit codes.

**Labelled evidence:**

- `src/flask/testing.py` lines 265–298 — CliRunner subclass invoking commands with the app's ScriptInfo.

```python
class FlaskCliRunner(CliRunner):
    """A :class:`~click.testing.CliRunner` for testing a Flask app's
    CLI commands. Typically created using
    :meth:`~flask.Flask.test_cli_runner`. See :ref:`testing-cli`.
    """

    def __init__(self, app: Flask, **kwargs: t.Any) -> None:
        self.app = app
        super().__init__(**kwargs)

    def invoke(  # type: ignore
        self, cli: t.Any = None, args: t.Any = None, **kwargs: t.Any
    ) -> t.Any:
        """Invokes a CLI command in an isolated environment. See
        :meth:`CliRunner.invoke <click.testing.CliRunner.invoke>` for
        full method documentation. See :ref:`testing-cli` for examples.

        If the ``obj`` argument is not given, passes an instance of
# … 16 more lines
```

- `src/flask/app.py` lines 690–705 — Creates the runner.

```python
    def test_cli_runner(self, **kwargs: t.Any) -> FlaskCliRunner:
        """Create a CLI runner for testing CLI commands.
        See :ref:`testing-cli`.

        Returns an instance of :attr:`test_cli_runner_class`, by default
        :class:`~flask.testing.FlaskCliRunner`. The Flask app object is
        passed as the first argument.

        .. versionadded:: 1.0
        """
        cls = self.test_cli_runner_class

        if cls is None:
            from .testing import FlaskCliRunner as cls

        return cls(self, **kwargs)  # type: ignore
```

- `docs/testing.rst` lines 245–272 — Docs for test_cli_runner.

```
Running Commands with the CLI Runner
------------------------------------

Flask provides :meth:`~flask.Flask.test_cli_runner` to create a
:class:`~flask.testing.FlaskCliRunner`, which runs CLI commands in
isolation and captures the output in a :class:`~click.testing.Result`
object. Flask's runner extends :doc:`Click's runner <click:testing>`,
see those docs for additional information.

Use the runner's :meth:`~flask.testing.FlaskCliRunner.invoke` method to
call commands in the same way they would be called with the ``flask``
command from the command line.

.. code-block:: python

    import click

    @app.cli.command("hello")
# … 10 more lines
```

*Note:* Task evidence corrected 2026-10-05 (approved by Avaneesh Kumar Verma). Was: Evidence cites testing.py L120-170 (FlaskClient); FlaskCliRunner is 265-298.

