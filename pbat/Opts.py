from dataclasses import dataclass, field, fields

ON_PUSH = 1

WINDOWS_2019 = "windows-2019"
WINDOWS_2022 = "windows-2022"
WINDOWS_LATEST = "windows-latest"

@dataclass
class Opts:
    debug: bool = False
    clean: bool = False
    curl_user_agent: str = None
    curl_proxy: str = None
    download_test: bool = True
    unzip_test: bool = True
    zip_test: bool = True
    github: bool = False
    github_workflow = False
    github_image: str = WINDOWS_LATEST
    github_on: int = ON_PUSH
    msys2_msystem: str = None
    use_sed: bool = False
    use_diff: bool = True
    env_path: list[str] = field(default_factory=list)
    clear_path: bool = False
    use_patch: bool = False
    need_curl_var: bool = False
    need_patch_var: bool = False
    env_policy: bool = False

def copy_opts(opts: Opts) -> Opts:
    res = Opts()
    for field in fields(opts):
        value = getattr(opts, field.name)
        if isinstance(value, list):
            value = list(value)
        setattr(res, field.name, value)
    return res