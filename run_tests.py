"""
run_tests.py
============
Lightweight test runner that executes pytest-style assertions using standard library.
"""
import sys

def main():
    failures = 0
    passed = 0
    
    # Import test modules
    try:
        from tests import test_pb_decoder, test_transcript, test_intelligence, test_wikilinks, test_markdown, test_relations
    except ImportError as e:
        print(f"Failed to import tests: {e}")
        sys.exit(1)
        
    test_modules = [
        ("test_pb_decoder", test_pb_decoder),
        ("test_transcript", test_transcript),
        ("test_intelligence", test_intelligence),
        ("test_wikilinks", test_wikilinks),
        ("test_markdown", test_markdown),
        ("test_relations", test_relations)
    ]
    
    for name, mod in test_modules:
        print(f"Running tests in {name}...")
        # Get all functions starting with test_
        funcs = [getattr(mod, f) for f in dir(mod) if f.startswith("test_") and callable(getattr(mod, f))]
        for func in funcs:
            func_name = func.__name__
            try:
                func()
                print(f"  [PASS] {func_name}")
                passed += 1
            except AssertionError as e:
                print(f"  [FAIL] {func_name}: AssertionError")
                failures += 1
            except Exception as e:
                print(f"  [ERROR] {func_name}: {e}")
                failures += 1
                
    print(f"\nTest Summary: {passed} passed, {failures} failed")
    import unittest
    from tests import test_studio
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_studio)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    failures += len(result.failures) + len(result.errors)
    print(f"Combined checks: {passed + result.testsRun} tests, {failures} failures")
    if failures > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
