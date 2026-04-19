(function () {
    function togglePasswordVisibility(button) {
        var targetId = button.getAttribute("data-target");
        var input = document.getElementById(targetId);
        if (!input) {
            return;
        }

        var showing = input.type === "text";
        input.type = showing ? "password" : "text";
        button.textContent = showing ? "Show" : "Hide";
        button.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    }

    function scorePassword(password) {
        var score = 0;
        if (password.length >= 8) score += 1;
        if (password.length >= 12) score += 1;
        if (/[A-Z]/.test(password)) score += 1;
        if (/[a-z]/.test(password)) score += 1;
        if (/[0-9]/.test(password)) score += 1;
        if (/[^A-Za-z0-9]/.test(password)) score += 1;
        return score;
    }

    function updatePasswordMeter(password) {
        var bar = document.getElementById("passwordMeterBar");
        var text = document.getElementById("passwordStrengthText");
        if (!bar || !text) {
            return;
        }

        var score = scorePassword(password);
        var width = "22%";
        var label = "very weak";
        var color = "#fda29b";

        if (score >= 2) {
            width = "40%";
            label = "weak";
            color = "#f79009";
        }
        if (score >= 4) {
            width = "65%";
            label = "medium";
            color = "#2e90fa";
        }
        if (score >= 6) {
            width = "100%";
            label = "strong";
            color = "#12b76a";
        }

        bar.style.width = width;
        bar.style.backgroundColor = color;
        text.textContent = "Strength: " + label;
    }

    function bindLoginValidation() {
        var form = document.getElementById("loginForm");
        var error = document.getElementById("loginError");
        if (!form || !error) {
            return;
        }

        form.addEventListener("submit", function (event) {
            var identity = document.getElementById("identity");
            var password = document.getElementById("password");
            var message = "";

            if (!identity || !identity.value.trim()) {
                message = "Email or username is required.";
            } else if (!password || password.value.length < 8) {
                message = "Password must be at least 8 characters.";
            }

            if (message) {
                event.preventDefault();
                error.textContent = message;
            } else {
                error.textContent = "";
            }
        });
    }

    function bindSignupValidation() {
        var form = document.getElementById("signupForm");
        var error = document.getElementById("signupError");
        var passwordInput = document.getElementById("password");
        if (!form || !error) {
            return;
        }

        if (passwordInput) {
            passwordInput.addEventListener("input", function () {
                updatePasswordMeter(passwordInput.value);
            });
        }

        form.addEventListener("submit", function (event) {
            var fullName = document.getElementById("full_name");
            var email = document.getElementById("email");
            var username = document.getElementById("username");
            var password = document.getElementById("password");
            var confirmPassword = document.getElementById("confirm_password");
            var message = "";

            if (!fullName || fullName.value.trim().length < 2) {
                message = "Full name must be at least 2 characters.";
            } else if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
                message = "Please enter a valid email address.";
            } else if (!username || username.value.trim().length < 3 || /\s/.test(username.value)) {
                message = "Username must be at least 3 characters and contain no spaces.";
            } else if (!password || password.value.length < 8) {
                message = "Password must be at least 8 characters.";
            } else if (password.value !== confirmPassword.value) {
                message = "Password and confirm password do not match.";
            }

            if (message) {
                event.preventDefault();
                error.textContent = message;
            } else {
                error.textContent = "";
            }
        });
    }

    document.querySelectorAll(".toggle-password").forEach(function (button) {
        button.addEventListener("click", function () {
            togglePasswordVisibility(button);
        });
    });

    bindLoginValidation();
    bindSignupValidation();
})();
