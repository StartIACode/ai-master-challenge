from app.normalize import normalize


def test_lowercase_and_punct():
    assert normalize("Hello, WORLD! Printer 2 is DOWN.") == "hello world printer down"


def test_removes_email_url_numbers():
    out = normalize("contact joao@x.com http://a.b 123456 ticket")
    assert "joao" not in out and "http" not in out and "123456" not in out


def test_idempotent():
    s = "The VPN is not connecting, please help!!"
    assert normalize(normalize(s)) == normalize(s)


def test_keeps_domain_words():
    assert "vpn" in normalize("The VPN is not connecting")


# --- extra coverage beyond the plan ---


def test_empty_and_none_are_safe():
    assert normalize("") == ""
    assert normalize(None) == ""  # type: ignore[arg-type]
    assert normalize("   \n\t ") == ""


def test_removes_pt_stopwords_and_keeps_accents():
    out = normalize("Olá, eu não consigo acessar o sistema de RH")
    assert out == "não consigo acessar sistema rh"


def test_short_numbers_and_underscores_are_dropped():
    assert normalize("user_name 42 and 7 disks") == "user name disks"


def test_idempotent_on_messy_input():
    s = "Re: [Ticket #4521] e-mail down!!! www.intranet.corp/help  __init__ 2024-01-01"
    assert normalize(normalize(s)) == normalize(s)
