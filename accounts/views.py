from rest_framework import generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from .models import Student, Teacher, User
from .permissions import IsAdminRole, IsTeacherOrAdmin
from .serializers import (
    MeSerializer,
    RegisterSerializer,
    StudentSerializer,
    TeacherSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(MeSerializer(user, context={"request": request}).data, status=201)


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("id")
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["role", "is_active"]
    search_fields = ["name", "email"]

    @action(
        detail=False,
        methods=["get", "patch"],
        permission_classes=[permissions.IsAuthenticated],
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def me(self, request):
        if request.method == "PATCH":
            serializer = MeSerializer(
                request.user, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(MeSerializer(request.user, context={"request": request}).data)


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related("user").order_by("id")
    serializer_class = StudentSerializer
    search_fields = ["student_number", "user__name", "user__email"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsTeacherOrAdmin()]
        return [IsAdminRole()]


class TeacherViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.select_related("user").order_by("id")
    serializer_class = TeacherSerializer
    search_fields = ["employee_number", "user__name", "user__email"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [IsAdminRole()]