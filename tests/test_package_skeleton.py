import importlib
import unittest


REQUIRED_MODULES = (
    "digital_fruit_fly",
    "digital_fruit_fly.arena",
    "digital_fruit_fly.brain",
    "digital_fruit_fly.body",
    "digital_fruit_fly.bridge",
    "digital_fruit_fly.behavior",
    "digital_fruit_fly.observability",
    "digital_fruit_fly.runtime",
)


class TestPackageSkeleton(unittest.TestCase):
    def test_required_modules_import_when_package_skeleton_exists(self) -> None:
        # Given: the Digital Fruit Fly package contract lists required modules.
        # When: each required module is imported in a fresh test process.
        imported = [importlib.import_module(name) for name in REQUIRED_MODULES]

        # Then: every module resolves to its requested import name.
        self.assertEqual([module.__name__ for module in imported], list(REQUIRED_MODULES))


if __name__ == "__main__":
    unittest.main()
