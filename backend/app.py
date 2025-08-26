    }
    async with httpx.AsyncClient(timeout=DEFAULT_PER_TEST_SECONDS) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenRouter error: {resp.status_code} - {resp.text}")
    body = resp.json()
    code = body["choices"][0]["message"]["content"]
    return _clean_code(code)


# --------- Cleanup ---------
def _clean_code(code: str) -> str:
    code = str(code).strip()
    code = re.sub(r"<think>.*?</think>", "", code, flags=re.DOTALL)
    if code.startswith("```"):
        code = "\n".join(code.split("\n")[1:])
    if code.endswith("```"):
        code = "\n".join(code.split("\n")[:-1])
    return code.strip()


# --------- Executor ---------
async def run_generated_code(code: str, base_url: str, timeout_s: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    try:
        compiled = compile(code, "<generated_tests>", "exec")
    except Exception as e:
        tb = traceback.format_exc()
        raise RuntimeError(f"Generated code failed to compile: {e}\n{tb}\nCODE:\n{code}")

    module_ns: Dict[str, Any] = {}
    exec(compiled, {"__builtins__": __builtins__}, module_ns)

    test_fns = [(n, f) for n, f in module_ns.items() if callable(f) and n.startswith("test_")]
    if not test_fns:
        raise RuntimeError("No test functions found in generated code.")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        for name, fn in test_fns:
            start = time.time()
            result = {"test_case": name, "status": "Passed", "time_taken": "", "error": ""}
            try:
                sig = inspect.signature(fn)
                params = list(sig.parameters.keys())
                args = []
                if len(params) >= 1:
                    args.append(page)
                if len(params) >= 2:
                    args.append(context)
                if len(params) >= 3:
                    args.append(browser)
                await asyncio.wait_for(fn(*args), timeout=timeout_s)
            except AssertionError as e:
                result["status"] = "Failed"
                result["error"] = f"Assertion failed: {str(e)}"
            except Exception as e:
                result["status"] = "Failed"
                result["error"] = f"Error: {e}\n{traceback.format_exc()}"
            finally:
                result["time_taken"] = f"{int(time.time() - start)}s"
                results.append(result)

        await context.close()
        await browser.close()

    return results


# --------- Save Logs ---------
def save_logs(code: str, results: List[Dict[str, Any]]) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname_code = os.path.join(LOGS_DIR, f"{timestamp}_code.py")
    fname_results = os.path.join(LOGS_DIR, f"{timestamp}_results.json")
    with open(fname_code, "w", encoding="utf-8") as f:
        f.write(code)
    with open(fname_results, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return timestamp


# --------- Endpoints ---------
@app.post("/run_tests")
async def run_tests(request: Request):
    data = await request.json()
    url = (data.get("url") or "").strip()
    text = (data.get("test_cases_text") or "").strip()
    engine = (data.get("engine") or "ollama").lower()
    timeout = int(data.get("max_test_seconds") or DEFAULT_PER_TEST_SECONDS)

    if not url or not text:
        raise HTTPException(status_code=400, detail="Missing input")

    site_context = await collect_dom_context(url)

    try:
        if engine == "ollama":
            code = await call_ollama_for_code(text, site_context)
        elif engine == "openrouter":
            code = await call_openrouter_for_code(text, site_context)
        else:
            raise HTTPException(status_code=400, detail="Invalid engine. Use 'ollama' or 'openrouter'.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {str(e)}")

    try:
        results = await run_generated_code(code, url, timeout)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")

    ts = save_logs(code, results)
    return {"engine": engine, "results": results, "raw_code": code, "log_id": ts}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8008, log_level="info")
