import React, { useState, useEffect, useContext } from 'react';
import { AuthContext } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { Button, buttonVariants } from './ui/button';
import { Input } from './ui/input';
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"

const Login: React.FC = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const auth = useContext(AuthContext);

    useEffect(() => {
        if (auth?.user) {
            navigate('/');
        }
    }, [auth, navigate]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        if (auth) {
            try {
                const { user, error } = await auth.login(email, password);
                if (error) throw error;
                if (user) {
                    console.log('Login successful');
                    navigate('/models');
                }
            } catch (error) {
                console.error('Login failed:', error);
                setError('Invalid email or password');
            }
        }
    };

    return (
        <div className="max-w-md mx-auto mt-8">
            <Card>
                <CardHeader>
                    <CardTitle>Login</CardTitle>
                    <CardDescription>Please enter your details.</CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit}>
                        <div className="mb-4">
                            <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="email">
                                Email
                            </label>
                            <Input
                                id="email"
                                type="email"
                                placeholder="Email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                            />
                        </div>
                        <div className="mb-6">
                            <label className="block text-gray-700 text-sm font-bold mb-2" htmlFor="password">
                                Password
                            </label>
                            <Input
                                id="password"
                                type="password"
                                placeholder="******************"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                            />
                        </div>
                        {error && <p className="text-red-500 text-xs italic mb-4">{error}</p>}
                        <div className="flex justify-end">
                            <Button type="submit" variant="outline" className="hover:bg-gray-900 hover:text-white">Sign In</Button>
                        </div>
                    </form>
                </CardContent>
                <CardFooter>
                    <p className="text-sm text-gray-500">Don't have an account? <Link className={buttonVariants({ variant: "outline" }) + " hover:bg-gray-900 hover:text-white"} to="/signup">Register</Link></p>
                </CardFooter>
            </Card>
        </div>
    );
}

export default Login;