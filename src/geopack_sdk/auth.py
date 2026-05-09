class AuthManager:
    def __init__(self, client):
        self.client = client
        self.token = None

    def login(self, username, password):
        """
        Authenticate with the Geopack API using username and password.
        """
        endpoint = "/auth/login" # Adjust based on actual route
        payload = {"username": username, "password": password}
        response = self.client.post(endpoint, json=payload)
        
        self.token = response.get("token")
        if self.token:
            self.client.session.headers.update({
                "Authorization": f"Bearer {self.token}"
            })
        return response

    def logout(self):
        self.token = None
        if "Authorization" in self.client.session.headers:
            del self.client.session.headers["Authorization"]
