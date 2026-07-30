from setuptools import find_namespace_packages, setup


setup(
    name="cli-anything-buzz",
    version="1.0.0",
    description="CLI-Anything harness for the Buzz collaboration platform",
    long_description=(
        "A stateful, secret-safe Click and REPL wrapper around Buzz's native "
        "agent-first Rust CLI."
    ),
    author="Kombiz",
    url="https://github.com/block/buzz",
    python_requires=">=3.10",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0",
        "prompt-toolkit>=3.0",
    ],
    extras_require={"dev": ["pytest>=7.0"]},
    package_data={
        "cli_anything.buzz": ["skills/*.md"],
    },
    entry_points={
        "console_scripts": [
            "cli-anything-buzz=cli_anything.buzz.buzz_cli:main",
        ],
    },
)
