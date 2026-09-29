# Browser E2E suite

Install the Python test tools once, if they are not already available:

```powershell
py -3.14 -m pip install pytest playwright
py -3.14 -m playwright install chromium
```

Run the complete operator-flow suite from the repository root:

```powershell
npm run test:e2e
```

The pytest session fixture starts the local Next development server in webpack mode on port `3141`, waits for HTTP readiness, blocks API requests to keep the UI offline, and stops the server after pytest exits. Fixture data is enabled with `?fixtures=1` only in tests that need it. Port `3141` must be free. The test command uses the `py -3.14` launcher to match the supported local Python environment.

The suite covers keyboard and rail navigation, Arabic RTL document metadata, fixture disclosure and offline honesty, cross-filtering, incident selection and j/k movement, privacy affordances, theme persistence, command-palette navigation, mobile overflow, and browser console errors.
